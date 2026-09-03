"""应用版本号唯一来源（v0.03 技术方案 §13）。

全部展示出口（页面 footer、/health、/api/admin/status）均引用此常量，
禁止在模板或接口中硬编码版本字符串。
"""

APP_VERSION = "v0.03.1"
