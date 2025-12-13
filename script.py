import functools
import inspect
import sys


def add_log_to_function(function_id, replace_original=True):
    """
    程序化地为函数添加输入输出日志

    参数:
        function_id: 可以是函数对象或字符串格式的"模块名.函数名"
        replace_original: 是否替换原始函数

    返回:
        装饰后的函数
    """
    # 获取目标函数
    if callable(function_id):
        print('callable')
        # 如果传入的是函数对象
        target_func = function_id
        module = inspect.getmodule(target_func)
        func_name = target_func.__name__
    else:
        print('not callable')
        # 如果传入的是字符串，格式应为"模块名.函数名"
        if '.' in function_id:
            module_name, func_name = function_id.rsplit('.', 1)
            module = sys.modules.get(module_name)
            if not module:
                print('no module')
                raise ValueError(f"模块 {module_name} 不存在")

            target_func = getattr(module, func_name, None)
            print(target_func)
            if not target_func:
                print('no target func')
                raise ValueError(f"函数 {func_name} 在模块 {module_name} 中不存在")
        else:
            # 假设是当前模块中的函数名
            caller_frame = inspect.currentframe().f_back
            module = inspect.getmodule(caller_frame)
            func_name = function_id
            target_func = getattr(module, func_name, None)
            if not target_func:
                print('no target func2')
                raise ValueError(f"函数 {func_name} 在当前模块中不存在")

    # 创建装饰后的函数
    @functools.wraps(target_func)
    def wrapped(*args, **kwargs):
        print('wrapped')
        print(f"调用 {target_func.__name__}:")
        print(f"  输入参数: args={args}, kwargs={kwargs}")
        result = target_func(*args, **kwargs)
        print(f"  返回值: {result}")
        return result

        # 替换原始函数（如果需要）

    if replace_original and module:
        print(f'set attr:{module} {func_name}')
        setattr(module, func_name, wrapped)

        # 关键步骤：在所有已加载模块中查找并替换函数引用
    original_func_id = id(target_func)
    replaced_count = 0

    for mod_name, mod in list(sys.modules.items()):
        # 跳过None模块
        if mod is None:
            continue

        # 检查模块的所有属性
        for attr_name in dir(mod):
            try:
                attr = getattr(mod, attr_name)
                # 检查是否是同一个函数对象(通过id比较)
                if id(attr) == original_func_id:
                    setattr(mod, attr_name, wrapped)
                    replaced_count += 1
                    print(f"在模块 {mod_name} 中替换了属性 {attr_name}")
            except:
                pass  # 忽略任何获取属性时的错误

    print(f"总共替换了 {replaced_count} 处函数引用")

    return wrapped


add_log_to_function("tool.reverse_string")
