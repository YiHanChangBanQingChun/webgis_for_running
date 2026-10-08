package dev.runningatlas.api.common;

import tools.jackson.databind.JsonNode;

/** Null-safe conversions shared by services reading loosely typed derived JSON. */
public final class JsonValues {
    private JsonValues() { }

    public static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isMissingNode() || value.isNull() ? null : value.asText();
    }

    public static double number(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.asDouble() : 0.0;
    }

    public static Double nullableNumber(JsonNode node) {
        return node != null && node.isNumber() ? node.asDouble() : null;
    }

    public static double round(double value, int digits) {
        double factor = Math.pow(10, digits);
        return Math.round(value * factor) / factor;
    }
}
