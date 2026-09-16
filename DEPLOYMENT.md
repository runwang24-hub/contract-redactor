# 私有服务器部署

本项目可公开源代码，同时将实际服务限制为内部访问。API Key 仅通过服务器环境变量提供，不进入镜像或 Git 仓库。

## 容器运行

```bash
docker build -t contract-redactor:latest .
docker run -d \
  --name contract-redactor \
  --restart unless-stopped \
  --env-file /opt/contract-redactor/.env \
  -p 127.0.0.1:8000:8000 \
  -v /opt/contract-redactor/runtime:/app/runtime \
  contract-redactor:latest
```

容器内已包含 LibreOffice Writer 和 Noto CJK 中文字体，因此 PDF、DOC、DOCX 均可处理。服务只绑定服务器回环地址，应通过 Nginx 等反向代理对外提供，并在代理层配置 HTTPS 和访问认证。

## 配置要求

复制 `.env.example` 为服务器上的 `/opt/contract-redactor/.env`，填写 AI MediaKit OCR 与火山方舟配置。不要把 `.env`、用户合同、OCR 中间图片或脱敏结果提交到 Git。

健康检查地址为 `/health`。默认上传上限为 60 MB；反向代理的请求体限制和读取超时应不低于应用配置。

## 数据清理

任务文件位于 `/opt/contract-redactor/runtime/web-jobs`。私有部署仍应定期清理过期任务目录，例如只保留最近 24 小时的输入、中间图像和输出文件。
