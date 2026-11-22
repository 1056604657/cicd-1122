package greeting

import (
	"strings"
)

// Greet returns a greeting for the provided name.
func Greet(name string) string {
	if strings.TrimSpace(name) == "" {
		return "Hello, world"
	}
	return "Hello, " + name
}
