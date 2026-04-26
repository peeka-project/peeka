#define _POSIX_C_SOURCE 200112L

#include <errno.h>
#include <netdb.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

/* We depend on the Python stable ABI, but avoid including Python.h directly. */
typedef ssize_t Py_ssize_t;

typedef struct _object PyObject;
typedef enum { PyGILState_LOCKED, PyGILState_UNLOCKED } PyGILState_STATE;

typedef int (*inquiry)(PyObject*);
typedef int (*traverseproc)(PyObject*, void*, void*);
typedef void (*freefunc)(void*);

typedef PyObject* (*PyCFunction)(PyObject*, PyObject*);

typedef struct PyMethodDef {
    const char* ml_name;
    PyCFunction ml_meth;
    int ml_flags;
    const char* ml_doc;
} PyMethodDef;

typedef struct PyModuleDef_Base {
    /* Simplified object header for stable ABI usage. */
    struct {
        Py_ssize_t ob_refcnt;
        void* ob_type;
    } ob_base;
    PyObject* (*m_init)(void);
    Py_ssize_t m_index;
    PyObject* m_copy;
} PyModuleDef_Base;

typedef struct PyModuleDef {
    PyModuleDef_Base m_base;
    const char* m_name;
    const char* m_doc;
    Py_ssize_t m_size;
    PyMethodDef* m_methods;
    void* m_slots;
    traverseproc m_traverse;
    inquiry m_clear;
    freefunc m_free;
} PyModuleDef;

#define Py_file_input 257
#define METH_VARARGS 0x0001

#define PyAPI_FUNC(ret_type) extern ret_type

PyAPI_FUNC(char*) PyBytes_AsString(PyObject*);
PyAPI_FUNC(PyObject*) PyDict_New(void);
PyAPI_FUNC(int) PyDict_SetItemString(PyObject* dp, const char* key, PyObject* item);
PyAPI_FUNC(void) PyErr_Clear(void);
PyAPI_FUNC(void) PyErr_Fetch(PyObject**, PyObject**, PyObject**);
PyAPI_FUNC(void) PyErr_NormalizeException(PyObject**, PyObject**, PyObject**);
PyAPI_FUNC(PyObject*) PyErr_Occurred(void);
PyAPI_FUNC(PyObject*) PyEval_EvalCode(PyObject*, PyObject*, PyObject*);
PyAPI_FUNC(PyGILState_STATE) PyGILState_Ensure(void);
PyAPI_FUNC(void) PyGILState_Release(PyGILState_STATE);
PyAPI_FUNC(PyObject*) PyImport_ImportModule(const char* name);
PyAPI_FUNC(PyObject*) PyModule_Create2(PyModuleDef* module, int apiver);
PyAPI_FUNC(PyObject*) PyModuleDef_Init(PyModuleDef*);
PyAPI_FUNC(PyObject*) PyObject_Repr(PyObject*);
PyAPI_FUNC(PyObject*) PyUnicode_AsUTF8String(PyObject* unicode);
PyAPI_FUNC(PyObject*) Py_CompileString(const char*, const char*, int);
PyAPI_FUNC(void) Py_DecRef(PyObject*);
PyAPI_FUNC(int) Py_IsInitialized(void);
PyAPI_FUNC(int) PyArg_ParseTuple(PyObject*, const char*, ...);
PyAPI_FUNC(PyObject*) PyLong_FromLong(long);

static int connect_client(uint16_t port);
static int sendall(int fd, const char* data, size_t length);
static int recvall(int fd, char** data, size_t* length);
static int run_script(const char* script, char** errmsg);
static int run_script_impl(const char* script, char** errmsg);
static char* peeka_pyerr_to_string(void);
static char* copy_string(const char* src);
static void run_client(uint16_t port);
static void* thread_body(void* arg);

static char*
copy_string(const char* src)
{
    size_t length = 0;
    char* dst = NULL;

    if (!src) {
        src = "";
    }

    length = strlen(src);
    dst = (char*)malloc(length + 1);
    if (!dst) {
        return NULL;
    }

    memcpy(dst, src, length + 1);
    return dst;
}

static int
connect_client(uint16_t port)
{
    struct addrinfo hints;
    struct addrinfo* all_addresses = NULL;
    struct addrinfo* curr_address = NULL;
    char port_str[6];
    int rv;
    int sockfd = -1;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    snprintf(port_str, sizeof(port_str), "%u", (unsigned int)port);
    rv = getaddrinfo(NULL, port_str, &hints, &all_addresses);
    if (rv != 0) {
        fprintf(stderr, "getaddrinfo() failed while trying to attach peeka: %s", gai_strerror(rv));
        return -1;
    }

    for (curr_address = all_addresses; curr_address != NULL; curr_address = curr_address->ai_next) {
        sockfd = socket(curr_address->ai_family, curr_address->ai_socktype, curr_address->ai_protocol);
        if (sockfd == -1) {
            continue;
        }

        while (connect(sockfd, curr_address->ai_addr, curr_address->ai_addrlen) == -1) {
            if (errno == EINTR) {
                continue;
            }
            close(sockfd);
            sockfd = -1;
            break;
        }

        if (sockfd != -1) {
            break;
        }
    }

    freeaddrinfo(all_addresses);
    return sockfd;
}

static int
sendall(int fd, const char* data, size_t length)
{
    while (length > 0) {
        ssize_t ret = send(fd, data, length, 0);
        if (ret < 0) {
            if (errno == EINTR) {
                continue;
            }
            return 0;
        }

        data += (size_t)ret;
        length -= (size_t)ret;
    }

    return 1;
}

static int
recvall(int fd, char** data, size_t* length)
{
    char buf[4096];
    char* out = NULL;
    size_t used = 0;
    size_t cap = 0;

    *data = NULL;
    *length = 0;

    while (1) {
        ssize_t ret = recv(fd, buf, sizeof(buf), 0);
        if (ret < 0) {
            if (errno == EINTR) {
                continue;
            }
            free(out);
            return 0;
        }

        if (ret == 0) {
            break;
        }

        if (used + (size_t)ret + 1 > cap) {
            size_t new_cap = cap ? cap : 4096;
            char* new_out;
            while (new_cap < used + (size_t)ret + 1) {
                new_cap *= 2;
            }
            new_out = (char*)realloc(out, new_cap);
            if (!new_out) {
                free(out);
                return 0;
            }
            out = new_out;
            cap = new_cap;
        }

        memcpy(out + used, buf, (size_t)ret);
        used += (size_t)ret;
    }

    if (!out) {
        out = (char*)malloc(1);
        if (!out) {
            return 0;
        }
    }

    out[used] = '\0';
    *data = out;
    *length = used;
    return 1;
}

/* Clear the error indicator and return a newly allocated string. */
static char*
peeka_pyerr_to_string(void)
{
    char* ret = NULL;
    PyObject* type = NULL;
    PyObject* val = NULL;
    PyObject* tb = NULL;
    PyObject* exc_repr = NULL;
    PyObject* utf8 = NULL;
    char* bytes_str = NULL;

    if (!PyErr_Occurred()) {
        return copy_string("");
    }

    PyErr_Fetch(&type, &val, &tb);
    PyErr_NormalizeException(&type, &val, &tb);

    exc_repr = PyObject_Repr(val);
    if (!exc_repr) {
        PyErr_Clear();
        ret = copy_string("unknown exception (`repr(exc)` failed)!");
        goto done;
    }

    utf8 = PyUnicode_AsUTF8String(exc_repr);
    if (!utf8) {
        PyErr_Clear();
        ret = copy_string("unknown exception (`repr(exc).encode('utf-8')` failed)!");
        goto done;
    }

    bytes_str = PyBytes_AsString(utf8);
    if (!bytes_str) {
        PyErr_Clear();
        ret = copy_string("unknown exception (`PyBytes_AsString` failed)!");
        goto done;
    }

    ret = copy_string(bytes_str);

done:
    Py_DecRef(utf8);
    Py_DecRef(exc_repr);
    Py_DecRef(type);
    Py_DecRef(val);
    Py_DecRef(tb);
    if (!ret) {
        ret = copy_string("unknown exception (out of memory)");
    }
    return ret;
}

static int
run_script_impl(const char* script, char** errmsg)
{
    int rc;
    PyObject* builtins = NULL;
    PyObject* globals = NULL;
    PyObject* code = NULL;
    PyObject* mod = NULL;
    int success = 0;

    builtins = PyImport_ImportModule("builtins");
    if (!builtins) {
        goto done;
    }

    globals = PyDict_New();
    if (!globals) {
        goto done;
    }

    rc = PyDict_SetItemString(globals, "__builtins__", builtins);
    if (0 != rc) {
        goto done;
    }

    code = Py_CompileString(script, "_peeka_attach_hook.py", Py_file_input);
    if (!code) {
        goto done;
    }

    mod = PyEval_EvalCode(code, globals, globals);
    if (!mod) {
        goto done;
    }

    success = 1;

done:
    Py_DecRef(mod);
    Py_DecRef(code);
    Py_DecRef(globals);
    Py_DecRef(builtins);

    *errmsg = peeka_pyerr_to_string();
    return success;
}

static int
run_script(const char* script, char** errmsg)
{
    PyGILState_STATE gstate;
    int ret;

    if (!Py_IsInitialized()) {
        *errmsg = copy_string("Python is not initialized");
        return 0;
    }

    gstate = PyGILState_Ensure();
    ret = run_script_impl(script, errmsg);
    PyGILState_Release(gstate);
    return ret;
}

static void
run_client(uint16_t port)
{
    int sock = connect_client(port);
    char* script = NULL;
    size_t script_len = 0;
    char* errmsg = NULL;
    int success;

    if (sock == -1) {
        fprintf(stderr, "peeka attach failed!\n");
        return;
    }

    if (!recvall(sock, &script, &script_len)) {
        (void)script_len;
        fprintf(stderr, "peeka attach socket read error!\n");
        close(sock);
        return;
    }

    success = run_script(script, &errmsg);
    if (!success && errmsg) {
        sendall(sock, errmsg, strlen(errmsg));
    }

    free(errmsg);
    free(script);
    close(sock);
}

static void*
thread_body(void* arg)
{
    int rc = pthread_detach(pthread_self());
    uint16_t port;

    if (0 != rc) {
        fprintf(stderr, "Failed to detach thread!\n");
    }

    port = (uint16_t)(uintptr_t)arg;
    run_client(port);
    return NULL;
}

__attribute__((visibility("default"))) int
peeka_spawn_agent(int port)
{
    pthread_t thread;
    return pthread_create(&thread, NULL, &thread_body, (void*)(uintptr_t)port);
}

static PyObject*
py_peeka_spawn_agent(PyObject* self, PyObject* args)
{
    int port;
    int rc;

    (void)self;

    if (!PyArg_ParseTuple(args, "i", &port)) {
        return NULL;
    }

    rc = peeka_spawn_agent(port);
    return PyLong_FromLong((long)rc);
}

static PyMethodDef INJECT_METHODS[] = {
        {"peeka_spawn_agent", py_peeka_spawn_agent, METH_VARARGS, "Spawn injector client thread."},
        {NULL, NULL, 0, NULL},
};

static PyModuleDef INJECT_MODULE_DEF = {
        {0},
        "_inject",
        NULL,
        -1,
        INJECT_METHODS,
        NULL,
        NULL,
        NULL,
        NULL,
};

__attribute__((visibility("default"))) PyObject*
PyInit__inject(void)
{
    if (!PyModuleDef_Init(&INJECT_MODULE_DEF)) {
        return NULL;
    }
    return PyModule_Create2(&INJECT_MODULE_DEF, 3);
}
