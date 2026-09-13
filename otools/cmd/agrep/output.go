package main

import "strings"

// assemble builds the final stdout: rg output plus, when any hint fired, the
// Reminder block — "\n\nReminder:\n" + hints joined by "\n" + trailing "\n".
// No hints means the rg output is returned untouched, byte for byte.
func assemble(content string, hints []string) string {
	if len(hints) == 0 {
		return content
	}
	return content + "\n\nReminder:\n" + strings.Join(hints, "\n") + "\n"
}
