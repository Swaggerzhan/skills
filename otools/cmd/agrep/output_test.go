package main

import "testing"

func TestAssembleNoHints(t *testing.T) {
	content := "Found 1 matches\n\na.cc:\n  Line 1: x"
	if got := assemble(content, nil); got != content {
		t.Fatalf("content must be untouched, got %q", got)
	}
}

func TestAssembleHints(t *testing.T) {
	got := assemble("No files found", []string{"[proto_gen_filter]: a", "[dep_search]: b"})
	want := "No files found\n\nReminder:\n[proto_gen_filter]: a\n[dep_search]: b\n"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
