from tool import reverse_string

if __name__ == '__main__':
    while True:
        user_input = input("请输入一个字符串: ")
        reversed_string = reverse_string(user_input)
        print("反转后的字符串:", reversed_string)
