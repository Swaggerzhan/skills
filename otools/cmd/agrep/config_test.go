package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadConfigMissing(t *testing.T) {
	cfg, err := loadConfig(filepath.Join(t.TempDir(), "nope.jsonc"))
	if err != nil || cfg != nil {
		t.Fatalf("missing file: got cfg=%v err=%v, want nil,nil", cfg, err)
	}
}

func TestLoadConfigFull(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agrep.jsonc")
	os.WriteFile(path, []byte(`{
  // 记录配置
  "mysql": {
    "endpoint": "db.internal", // 无端口默认 3306
    "username": "u",
    "password": "p//with:chars",
    "database": "d",
  },
  "proto_gen_file_filter": false,
}`), 0o644)
	cfg, err := loadConfig(path)
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if cfg.MySQL == nil {
		t.Fatal("mysql config nil")
	}
	if cfg.MySQL.hostPort() != "db.internal:3306" {
		t.Fatalf("hostPort: %q", cfg.MySQL.hostPort())
	}
	if cfg.MySQL.Password != "p//with:chars" {
		t.Fatalf("password mangled: %q", cfg.MySQL.Password)
	}
	if cfg.filterEnabled() {
		t.Fatal("proto_gen_file_filter: false must disable the filter")
	}
}

func TestLoadConfigIncompleteMySQL(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agrep.jsonc")
	os.WriteFile(path, []byte(`{"mysql": {"endpoint": "h:3307", "username": "u"}}`), 0o644)
	cfg, err := loadConfig(path)
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if cfg.MySQL != nil {
		t.Fatalf("incomplete mysql should be dropped, got %+v", cfg.MySQL)
	}
	if !cfg.filterEnabled() {
		t.Fatal("filter must default to enabled when the field is absent")
	}
}

func TestFilterEnabledNilConfig(t *testing.T) {
	var cfg *config
	if !cfg.filterEnabled() {
		t.Fatal("filter must default to enabled when config is absent")
	}
}

func TestLoadConfigInvalid(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agrep.jsonc")
	os.WriteFile(path, []byte(`{oops`), 0o644)
	cfg, err := loadConfig(path)
	if err == nil || cfg != nil {
		t.Fatalf("invalid: got cfg=%v err=%v", cfg, err)
	}
}
