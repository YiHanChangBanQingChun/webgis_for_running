package dev.runningatlas.api.common;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 统一业务异常处理器。
 *
 * <p>{@code @RestControllerAdvice} 拦截控制器调用链中抛出的 ApiException， 保持错误响应的 timestamp、detail
 * 字段一致；这里没有吞掉所有未知异常。
 */
@RestControllerAdvice
public class ApiExceptionHandler {
    /**
     * 将业务异常的状态和说明转换为统一 JSON 错误响应。
     *
     * @param exception 调用链中抛出的业务异常
     * @return 携带明确 HTTP 状态码及 JSON 内容的响应
     */
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> handle(ApiException exception) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("timestamp", OffsetDateTime.now().toString());
        body.put("detail", exception.getMessage());
        return ResponseEntity.status(exception.status()).body(body);
    }
}
