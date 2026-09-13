package main

import (
	"encoding/json"
	"testing"
)

func TestStripJSONCComments(t *testing.T) {
	src := `{
  // line comment
  "a": 1, /* block comment */ "b": "x",
  "c": "http://host/path", // url with //
  "d": "has /* not a comment */ chars",
}`
	var got map[string]any
	if err := json.Unmarshal(stripJSONC([]byte(src)), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got["a"] != float64(1) || got["b"] != "x" {
		t.Fatalf("unexpected: %v", got)
	}
	if got["c"] != "http://host/path" {
		t.Fatalf("string content mangled: %v", got["c"])
	}
	if got["d"] != "has /* not a comment */ chars" {
		t.Fatalf("block-comment chars inside string mangled: %v", got["d"])
	}
}

func TestStripJSONCTrailingCommas(t *testing.T) {
	src := `{"a": [1, 2,], "b": {"c": 3,}, "d": "x,}",}`
	var got map[string]any
	if err := json.Unmarshal(stripJSONC([]byte(src)), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got["d"] != "x,}" {
		t.Fatalf("comma inside string mangled: %v", got["d"])
	}
}

func TestStripJSONCEscapedQuote(t *testing.T) {
	src := `{"a": "he said \"hi\" // tail",}`
	var got map[string]any
	if err := json.Unmarshal(stripJSONC([]byte(src)), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got["a"] != `he said "hi" // tail` {
		t.Fatalf("escaped quote handling broken: %v", got["a"])
	}
}
