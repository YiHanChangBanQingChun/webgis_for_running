FROM python:3.13-alpine

WORKDIR /srv/backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_WEBGIS_DATA_DIR=/data/processed

# 先安装固定的核心依赖，修改应用代码时可以复用依赖安装层。
COPY requirements-core.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt \
    && addgroup -S webgis \
    && adduser -S -G webgis webgis

# 只打包 API 源代码，运行数据通过 Compose 单独挂载。
COPY --chown=webgis:webgis app ./app
USER webgis
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
