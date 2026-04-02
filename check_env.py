#!/usr/bin/env python
"""
启动验证脚本
检查环境配置并测试关键依赖
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_python_version():
    """检查 Python 版本"""
    print("[1/5] 检查 Python 版本...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"  ✗ Python {version.major}.{version.minor}.{version.micro} (需要 >= 3.8)")
        return False


def check_dependencies():
    """检查依赖包"""
    print("[2/5] 检查依赖包...")
    required = [
        'volcenginesdkarkruntime',
        'pyautogui',
        'PIL',
        'pyperclip',
        'dotenv'
    ]
    
    missing = []
    for package in required:
        try:
            if package == 'PIL':
                __import__('PIL')
            elif package == 'dotenv':
                __import__('dotenv')
            else:
                __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} (未安装)")
            missing.append(package)
    
    return len(missing) == 0


def check_config():
    """检查配置"""
    print("[3/5] 检查配置...")
    try:
        from computer_use.config import config
        
        # 检查 API 密钥
        if config.api_key:
            # 隐藏部分密钥
            key = config.api_key
            masked = key[:8] + '...' + key[-4:] if len(key) > 12 else '***'
            print(f"  ✓ ARK_API_KEY: {masked}")
        else:
            print(f"  ✗ ARK_API_KEY: 未设置")
            return False
        
        print(f"  ✓ 模型: {config.model}")
        print(f"  ✓ API地址: {config.base_url}")
        print(f"  ✓ 截图保存: {'是' if config.save_screenshot else '否'}")
        
        return True
    except Exception as e:
        print(f"  ✗ 配置加载失败: {e}")
        return False


def check_imports():
    """检查模块导入"""
    print("[4/5] 检查模块导入...")
    try:
        from computer_use.config import config
        print("  ✓ computer_use.config")
        
        from computer_use.screenshot import capture_screenshot
        print("  ✓ computer_use.screenshot")
        
        from computer_use.action_parser import parse_action
        print("  ✓ computer_use.action_parser")
        
        from computer_use.action_executor import execute_action
        print("  ✓ computer_use.action_executor")
        
        from computer_use.agent import ComputerUseAgent
        print("  ✓ computer_use.agent")
        
        return True
    except Exception as e:
        print(f"  ✗ 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_screenshot():
    """测试截图功能"""
    print("[5/5] 测试截图功能...")
    try:
        from computer_use.screenshot import capture_screenshot
        
        print("  正在截图...")
        screenshot, path = capture_screenshot(save=False)
        
        if screenshot:
            width, height = screenshot.size
            print(f"  ✓ 截图成功: {width}x{height}")
            return True
        else:
            print("  ✗ 截图失败")
            return False
    except Exception as e:
        print(f"  ✗ 截图测试失败: {e}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("Computer Use Tool - 启动验证")
    print("="*60)
    print()
    
    # 运行所有检查
    checks = [
        check_python_version(),
        check_dependencies(),
        check_config(),
        check_imports(),
        test_screenshot()
    ]
    
    print()
    print("="*60)
    
    # 计算结果
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"✓ 所有检查通过 ({passed}/{total})")
        print()
        print("您可以开始使用 Computer Use Tool！")
        print()
        print("示例命令:")
        print("  python -m computer_use              # 交互模式")
        print("  python -m computer_use '打开浏览器'  # 单次任务")
        return 0
    else:
        print(f"✗ 部分检查未通过 ({passed}/{total})")
        print()
        print("请修复上述问题后再试。")
        
        if not checks[1]:  # 依赖检查失败
            print()
            print("提示: 运行以下命令安装依赖:")
            print("  pip install -r requirements.txt")
        
        if not checks[2]:  # 配置检查失败
            print()
            print("提示: 请设置 ARK_API_KEY 环境变量或创建 .env 文件")
            print("  cp .env.example .env")
            print("  # 编辑 .env 文件，填入你的 API 密钥")
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
