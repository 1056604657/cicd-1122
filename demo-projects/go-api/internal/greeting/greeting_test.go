package greeting

import "testing"

func TestGreetWithName(t *testing.T) {
	if got := Greet("GitLab"); got != "Hello, GitLab" {
		t.Fatalf("Greet(GitLab) = %q, want %q", got, "Hello, GitLab")
	}
}

func TestGreetWithBlankName(t *testing.T) {
	if got := Greet("   "); got != "Hello, world" {
		t.Fatalf("Greet(blank) = %q, want %q", got, "Hello, world")
	}
}
