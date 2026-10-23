package dev.runningatlas.api.common;

import org.springframework.http.HttpStatus;

/**
 * 可预期的 API 业务异常，携带 HTTP 状态码和可向前端展示的错误信息。
 *
 * <p>继承 RuntimeException，业务方法无需逐层声明 throws；统一异常处理器负责转换响应。
 */
public class ApiException extends RuntimeException {
    private final HttpStatus status;

    /**
     * 保存 HTTP 状态，并将说明传给父类，供异常处理器通过 getMessage 读取。
     *
     * @param status 响应 HTTP 状态码
     * @param message 可向前端展示的错误说明
     */
    public ApiException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    /**
     * 读取此业务异常对应的 HTTP 状态码。
     *
     * @return 该异常对应的 HTTP 状态码
     */
    public HttpStatus status() {
        return status;
    }
}
