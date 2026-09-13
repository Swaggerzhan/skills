package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// config mirrors ~/.config/otools/agrep.jsonc. A missing file, a parse
// failure, or any missing mysql field disables recording. The protobuf
// generated-code filter is enabled by default and only an explicit
// "proto_gen_file_filter": false turns it off.
type config struct {
	MySQL              *mysqlConfig `json:"mysql"`
	ProtoGenFileFilter *bool        `json:"proto_gen_file_filter"`
}

// filterEnabled reports whether the protobuf generated-code filter is on
// (default true, including when the whole config is absent).
func (c *config) filterEnabled() bool {
	return c == nil || c.ProtoGenFileFilter == nil || *c.ProtoGenFileFilter
}

type mysqlConfig struct {
	Endpoint string `json:"endpoint"` // host[:port], default port 3306
	Username string `json:"username"`
	Password string `json:"password"`
	Database string `json:"database"`
}

func defaultConfigPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return filepath.Join(home, ".config", "otools", "agrep.jsonc")
}

// loadConfig returns (nil, nil) when the file does not exist and (nil, err)
// when it exists but cannot be parsed.
func loadConfig(path string) (*config, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var cfg config
	if err := json.Unmarshal(stripJSONC(raw), &cfg); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if cfg.MySQL != nil && !cfg.MySQL.complete() {
		cfg.MySQL = nil
	}
	return &cfg, nil
}

func (m *mysqlConfig) complete() bool {
	return m != nil && m.Endpoint != "" && m.Username != "" && m.Database != ""
}

// hostPort normalizes the endpoint for the DSN: append the default port.
func (m *mysqlConfig) hostPort() string {
	ep := m.Endpoint
	if idx := strings.LastIndex(ep, ":"); idx > 0 && !strings.Contains(ep[idx+1:], "]") {
		return ep
	}
	return ep + ":3306"
}
