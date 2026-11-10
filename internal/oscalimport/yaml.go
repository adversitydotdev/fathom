package oscalimport

import (
	"fmt"
	"io"
	"strconv"
	"strings"
	"unicode"
)

func writeDocument(w io.Writer, comment string, body string) error {
	if comment != "" {
		if _, err := io.WriteString(w, "# "+comment+"\n"); err != nil {
			return err
		}
	}
	_, err := io.WriteString(w, body)
	return err
}

func yamlScalar(s string) string {
	if s == "" {
		return `""`
	}
	if needsQuote(s) {
		return strconv.Quote(s)
	}
	return s
}

func needsQuote(s string) bool {
	switch strings.ToLower(s) {
	case "true", "false", "null", "yes", "no", "on", "off", "~":
		return true
	}
	first := rune(s[0])
	if first == '&' || first == '*' || first == '!' || first == '%' || first == '@' || first == '`' ||
		first == '"' || first == '\'' || first == '[' || first == ']' || first == '{' || first == '}' ||
		first == ',' || first == '#' || first == '|' || first == '>' || first == '?' || first == ':' ||
		first == '-' || unicode.IsDigit(first) {
		return true
	}
	for _, r := range s {
		switch r {
		case ':', '#', '{', '}', '[', ']', ',', '&', '*', '!', '|', '>', '\'', '"', '%', '@', '`', '(', ')', '\n', '\t':
			return true
		}
	}
	if strings.TrimSpace(s) != s {
		return true
	}
	return false
}

func writeProse(b *strings.Builder, indent int, key, text string) {
	text = strings.TrimSpace(text)
	pad := strings.Repeat(" ", indent)
	if !strings.Contains(text, "\n") {
		fmt.Fprintf(b, "%s%s: >\n", pad, key)
		for _, line := range wrap(text, 76) {
			fmt.Fprintf(b, "%s  %s\n", pad, line)
		}
		return
	}
	fmt.Fprintf(b, "%s%s: |\n", pad, key)
	for _, line := range strings.Split(text, "\n") {
		if line == "" {
			fmt.Fprintf(b, "\n")
			continue
		}
		fmt.Fprintf(b, "%s  %s\n", pad, line)
	}
}

func wrap(s string, width int) []string {
	var lines []string
	var cur strings.Builder
	flush := func() {
		if cur.Len() > 0 {
			lines = append(lines, cur.String())
			cur.Reset()
		}
	}
	for _, word := range paramFields(s) {
		if cur.Len() == 0 {
			cur.WriteString(word)
			continue
		}
		if cur.Len()+1+len(word) > width {
			flush()
			cur.WriteString(word)
			continue
		}
		cur.WriteByte(' ')
		cur.WriteString(word)
	}
	flush()
	if len(lines) == 0 {
		return []string{""}
	}
	return lines
}

// paramFields splits on spaces and keeps a {{ parameter }} placeholder intact,
// including punctuation that sits against it.
func paramFields(s string) []string {
	var out []string
	var cur strings.Builder
	inParam := false
	flush := func() {
		if cur.Len() == 0 {
			return
		}
		out = append(out, cur.String())
		cur.Reset()
	}
	for i := 0; i < len(s); i++ {
		if !inParam && i+1 < len(s) && s[i] == '{' && s[i+1] == '{' {
			if cur.Len() > 0 && strings.Trim(cur.String(), ".,;:()[]") != "" {
				flush()
			}
			inParam = true
		}
		if !inParam && s[i] == ' ' {
			flush()
			continue
		}
		cur.WriteByte(s[i])
		if inParam && i > 0 && s[i] == '}' && s[i-1] == '}' {
			inParam = false
		}
	}
	flush()
	return out
}
