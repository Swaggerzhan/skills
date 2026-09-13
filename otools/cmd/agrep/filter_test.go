package main

import (
	"context"
	"errors"
	"reflect"
	"slices"
	"testing"
)

func TestExtractExts(t *testing.T) {
	cases := []struct {
		glob string
		want []string
	}{
		{"*.cc", []string{"cc"}},
		{"*.{h,cc}", []string{"h", "cc"}},
		{"src/**/Makefile", nil},
		{"*.{h,hpp,cpp,cc}", []string{"h", "hpp", "cpp", "cc"}},
		{"*.PB.H", []string{"h"}},
		{"README", nil},
	}
	for _, c := range cases {
		if got := extractExts(c.glob); !slices.Equal(got, c.want) {
			t.Errorf("extractExts(%q) = %v, want %v", c.glob, got, c.want)
		}
	}
}

func TestActiveGenPatterns(t *testing.T) {
	got := activeGenPatterns("*.h")
	want := []string{"*.pb.h", "*.grpc.pb.h", "*.pb.validate.h"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
	if got := activeGenPatterns("Makefile"); got != nil {
		t.Fatalf("Makefile: got %v want nil", got)
	}
	if got := activeGenPatterns("*.{go,proto}"); !slices.Contains(got, "*.pb.go") {
		t.Fatalf("go: got %v", got)
	}
}

func TestProbeFilteredFile(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		if name != "rg" {
			t.Fatalf("unexpected cmd %q", name)
		}
		if !slices.Contains(args, "--files") {
			t.Fatalf("args missing --files: %v", args)
		}
		return cmdResult{stdout: []byte("gen/addressbook.pb.h\ngen/other.pb.h\n"), code: 0}, nil
	})()
	got := probeFilteredFile(context.Background(), "/root", []string{"*.pb.h"})
	if got != "gen/addressbook.pb.h" {
		t.Fatalf("got %q", got)
	}
}

func TestProbeFilteredFileNone(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{code: 1}, nil // rg --files: no matches
	})()
	if got := probeFilteredFile(context.Background(), "/root", []string{"*.pb.h"}); got != "" {
		t.Fatalf("got %q want empty", got)
	}
}

func TestProbeFilteredFileError(t *testing.T) {
	defer swapRunCmd(t, func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error) {
		return cmdResult{}, errors.New("spawn failed")
	})()
	if got := probeFilteredFile(context.Background(), "/root", []string{"*.pb.h"}); got != "" {
		t.Fatalf("probe failure must yield no hint, got %q", got)
	}
}

// swapRunCmd replaces the process runner for one test.
func swapRunCmd(t *testing.T, fake func(ctx context.Context, dir string, maxOut int, name string, args ...string) (cmdResult, error)) func() {
	t.Helper()
	orig := runCmd
	runCmd = fake
	return func() { runCmd = orig }
}
