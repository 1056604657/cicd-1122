package com.example.javaapi;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

class JavaApiApplicationTest {

    @Test
    void greetShouldReturnHelloWithName() {
        Assertions.assertEquals("Hello, GitLab", JavaApiApplication.greet("GitLab"));
    }

    @Test
    void greetShouldFallbackToWorldWhenNameIsBlank() {
        Assertions.assertEquals("Hello, world", JavaApiApplication.greet(" "));
    }
}
