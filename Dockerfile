# CDIPTV Panel — 成都电信 IPTV 管理面板
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask croniter requests
# 脚本与网页模板打入镜像；真实配置 config.json 不随镜像发布（首次运行自动生成）
COPY config/ /app/config/
COPY templates/ /app/templates/
# 输出目录 + 数据目录（config.json 等持久化数据挂载点）
RUN mkdir -p /app/output /app/data
EXPOSE 8999
CMD ["python3", "/app/config/webapi.py"]
