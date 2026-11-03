# Multi-stage Dockerfile for BankOps Flutter Web
# Stage 1: Build Flutter Web application
FROM ghcr.io/cirruslabs/flutter:stable AS builder

WORKDIR /app
COPY pubspec.yaml pubspec.lock* ./
RUN flutter pub get

COPY . .
ARG API_BASE_URL=""
ARG GOOGLE_CLIENT_ID=""
ARG APP_BUILD_NUMBER=local
RUN flutter build web --release \
    --dart-define=API_BASE_URL=${API_BASE_URL} \
    --dart-define=GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID} \
    --dart-define=APP_ENV=production \
    --build-number="${APP_BUILD_NUMBER}" \
    && sed -i "s/__APP_BUILD_NUMBER__/${APP_BUILD_NUMBER}/g" build/web/index.html \
    && printf '{"app_name":"kho_tra_sua","version":"0.1.0","build_number":"%s"}\n' "${APP_BUILD_NUMBER}" > build/web/version.json

# Stage 2: Serve with lightweight Nginx Alpine
FROM nginx:alpine-slim

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts from builder stage
COPY --from=builder /app/build/web /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
