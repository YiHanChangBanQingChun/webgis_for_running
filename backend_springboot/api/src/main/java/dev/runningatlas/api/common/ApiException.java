package dev.runningatlas.api.common;

import org.springframework.http.HttpStatus;

/** Expected business error that can safely be exposed as an HTTP response. */
public class ApiException extends RuntimeException {
    private final HttpStatus status;

    public ApiException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus status() {
        return status;
    }
}
