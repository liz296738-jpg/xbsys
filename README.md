# 教师选班系统

使用 Python HTTP 服务运行原有教师选班页面，数据保存在 Supabase PostgreSQL 的独立 course_app schema。

## 启动

安装 requirements.txt 后，配置服务器环境变量 DATABASE_URL（Supabase Session Pooler，SSL）和 JXB_HOST=0.0.0.0，再运行 python app.py。Render 使用 PORT 指定监听端口。

教师入口为 /，管理入口为 /admin，数据库健康检查为 /healthz。

生产数据库由迁移初始化；运行账号只拥有业务 schema 的读写权限。数据库凭据只配置在服务器环境变量中。SQLite 数据库和原始登录日志均不进入版本控制。

部署构建中运行 python test_postgres.py，验证真实数据库上的选班、重复提交拦截、Excel 导出、日志持久化和未授权管理请求拦截。临时测试记录在事务结束后回滚。

原始业务规则保留：教师使用工号和姓名登录，管理员使用原管理员密码。

## 2026-11-27 更新

同步新版教师端和管理端：支持不选班时提交情况说明，后台和 Excel 导出包含说明；管理员接口允许从凭证中识别省略的课程号。

线上保留 Supabase 数据库；启动快照存入同一数据库中的私有 startup_snapshots 表，保留最近 15 份。SQLite 本地运行继续使用文件快照。更新不导入上传包中的本地数据库。
