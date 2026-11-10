package oscalimport

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode"
)

const specVersion = "0.1.0"

// Options selects one OSCAL catalog and where its OpenGRC objects are written.
type Options struct {
	FrameworkID string
	Name        string
	Publisher   string
	SourceURI   string
	SourcePath  string
	Commit      string
	Version     string
	OutDir      string
	// Resolve maps zero-padded SP 800-53 labels such as AC-02(03) onto a
	// framework that has already been imported. SP 800-171 reference links
	// use those labels.
	Resolve *Index
}

// Result counts what an import wrote.
type Result struct {
	FrameworkID  string
	Requirements int
	Withdrawn    int
	Mappings     int
	Modified     string
	Index        *Index
}

var (
	insertRE         = regexp.MustCompile(`\{\{\s*insert:\s*param,\s*([^}\s]+)\s*\}\}`)
	controlRefRE     = regexp.MustCompile(`^[A-Z]{2}-\d{2}(?:\(\d{2}\))?$`)
	controlDisplayRE = regexp.MustCompile(`^[A-Z]{2}-\d+(\(\d+\))?$`)
	partHrefRE       = regexp.MustCompile(`^#([a-z0-9][a-z0-9.-]*)_smt\.([a-z0-9.]+)$`)
	hashHrefRE       = regexp.MustCompile(`^#([a-z0-9][a-z0-9.-]*)$`)
)

// Import reads an OSCAL catalog and writes framework, requirement, and draft
// mapping files. A second import of the same framework replaces that
// framework's requirements and the mappings whose source is in it.
func Import(doc []byte, opt Options) (Result, error) {
	if opt.OutDir == "" {
		return Result{}, fmt.Errorf("output directory is required")
	}
	built, err := build(doc, opt)
	if err != nil {
		return Result{}, err
	}
	if err := writeLibrary(built.opt, built.stamp, built.reqs, built.maps); err != nil {
		return Result{}, err
	}
	return built.result(), nil
}

// IndexOnly resolves control labels in a catalog without writing files.
// Pass the result as Options.Resolve when a later catalog cites those labels.
func IndexOnly(doc []byte, frameworkID string) (*Index, error) {
	built, err := build(doc, Options{FrameworkID: frameworkID})
	if err != nil {
		return nil, err
	}
	return built.idx, nil
}

// WriteBundle writes the library manifest. Objects live in sibling files.
func WriteBundle(outDir, created, modified string) error {
	if created == "" {
		created = modified
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	body := "# " + generatedComment + "\n" + renderBundle(created, modified)
	return os.WriteFile(filepath.Join(outDir, "bundle.yaml"), []byte(body), 0o644)
}

type builtCatalog struct {
	opt   Options
	stamp string
	reqs  []requirement
	maps  []mapping
	idx   *Index
}

func (b builtCatalog) result() Result {
	withdrawn := 0
	for _, r := range b.reqs {
		if r.withdrawn {
			withdrawn++
		}
	}
	return Result{
		FrameworkID:  b.opt.FrameworkID,
		Requirements: len(b.reqs),
		Withdrawn:    withdrawn,
		Mappings:     len(b.maps),
		Modified:     b.stamp,
		Index:        b.idx,
	}
}

func build(doc []byte, opt Options) (builtCatalog, error) {
	if opt.FrameworkID == "" {
		return builtCatalog{}, fmt.Errorf("framework id is required")
	}
	if opt.Publisher == "" {
		opt.Publisher = "NIST"
	}
	var parsed catalogDoc
	if err := json.Unmarshal(doc, &parsed); err != nil {
		return builtCatalog{}, fmt.Errorf("parse catalog: %w", err)
	}
	cat := parsed.Catalog
	stamp, err := catalogTime(cat.Metadata.LastModified)
	if err != nil {
		return builtCatalog{}, err
	}
	if opt.Name == "" {
		opt.Name = cat.Metadata.Title
	}
	if opt.Version == "" {
		opt.Version = cat.Metadata.Version
	}

	resources := map[string]resource{}
	for _, r := range cat.BackMatter.Resources {
		resources[r.UUID] = r
	}
	families := map[string]string{}
	for _, g := range cat.Groups {
		if g.ID != "" {
			families[g.ID] = g.Title
		}
	}

	var reqs []requirement
	for _, g := range cat.Groups {
		for i := range g.Controls {
			collect(&reqs, &g.Controls[i], opt, stamp, nil, resources)
		}
	}
	idx := indexOf(opt.FrameworkID, reqs)

	var maps []mapping
	seen := map[string]struct{}{}
	for i := range reqs {
		got, extra, err := mappingsFor(reqs[i], idx, opt.Resolve, resources, families)
		if err != nil {
			return builtCatalog{}, err
		}
		reqs[i].external = append(reqs[i].external, extra...)
		for _, m := range got {
			if _, ok := seen[m.id]; ok {
				return builtCatalog{}, fmt.Errorf("duplicate mapping %s", m.id)
			}
			seen[m.id] = struct{}{}
			maps = append(maps, m)
		}
	}
	return builtCatalog{opt: opt, stamp: stamp, reqs: reqs, maps: maps, idx: idx}, nil
}

func collect(dst *[]requirement, c *control, opt Options, stamp string, inherited []tokenParam, resources map[string]resource) {
	local, byToken := paramsOf(c.Params)
	sortID := propValue(c.Props, "sort-id", "")
	display := displayID(c.Props, sortID, c.ID)
	localSlug := slug(c.ID)
	if sortID != "" && (strings.Contains(c.ID, "800_171") || strings.HasPrefix(sortID, "0")) {
		localSlug = slug(sortID)
	}
	class := "control"
	if c.Class == "SP800-53-enhancement" {
		class = "enhancement"
	}

	req := requirement{
		id:        "requirement--" + opt.FrameworkID + "-" + localSlug,
		localSlug: localSlug,
		oscalID:   c.ID,
		sortID:    sortID,
		zeroPad:   propValue(c.Props, "label", "zero-padded"),
		created:   stamp,
		modified:  stamp,
		displayID: display,
		name:      strings.TrimSpace(c.Title),
		framework: opt.FrameworkID,
		class:     class,
		withdrawn: propValue(c.Props, "status", "") == "withdrawn",
		links:     c.Links,
	}
	if req.name == "" {
		req.name = display
	}

	usedInherited := map[string]struct{}{}
	rewrite := func(prose string) string {
		return insertRE.ReplaceAllStringFunc(prose, func(match string) string {
			tok := strings.TrimSpace(insertRE.FindStringSubmatch(match)[1])
			if key, ok := byToken[tok]; ok {
				return "{{ " + key + " }}"
			}
			if p, ok := findInherited(tok, inherited); ok {
				if _, seen := usedInherited[p.key]; !seen {
					local = append(local, namedParam{key: p.key, label: p.label})
					usedInherited[p.key] = struct{}{}
				}
				return "{{ " + p.key + " }}"
			}
			key := paramKey(tok)
			if _, exists := byToken[key]; !exists {
				local = append(local, namedParam{key: key, label: tok})
				byToken[tok] = key
				byToken[key] = key
			}
			return "{{ " + byToken[tok] + " }}"
		})
	}

	if stmt := statementPartOf(c.Parts); stmt != nil {
		if strings.TrimSpace(stmt.Prose) != "" {
			req.statement = rewrite(stmt.Prose)
		}
		req.parts = flattenParts(stmt.Parts, nil, sortID, rewrite)
	}
	req.parameters = local
	req.external = citations(c.Links, resources, opt.Publisher, opt.Resolve)

	*dst = append(*dst, req)
	next := inheritParams(c.Params, byToken)
	for i := range c.Controls {
		collect(dst, &c.Controls[i], opt, stamp, next, resources)
	}
}

func inheritParams(ps []param, byToken map[string]string) []tokenParam {
	var out []tokenParam
	seen := map[string]struct{}{}
	add := func(token, key, label string) {
		if token == "" || key == "" {
			return
		}
		if _, ok := seen[token]; ok {
			return
		}
		seen[token] = struct{}{}
		out = append(out, tokenParam{token: token, key: key, label: label})
	}
	for _, p := range ps {
		label := strings.TrimSpace(p.Label)
		if label == "" {
			label = strings.TrimSpace(p.Usage)
		}
		if label == "" {
			label = p.ID
		}
		add(p.ID, byToken[p.ID], label)
		for _, pr := range p.Props {
			if pr.Name == "alt-identifier" {
				add(pr.Value, byToken[p.ID], label)
			}
		}
	}
	return out
}

func findInherited(token string, inherited []tokenParam) (tokenParam, bool) {
	for _, p := range inherited {
		if p.token == token {
			return p, true
		}
	}
	return tokenParam{}, false
}

func paramsOf(ps []param) ([]namedParam, map[string]string) {
	var list []namedParam
	byToken := map[string]string{}
	used := map[string]struct{}{}
	for _, p := range ps {
		key := paramKey(p.ID)
		base := key
		for n := 2; ; n++ {
			if _, ok := used[key]; !ok {
				break
			}
			key = fmt.Sprintf("%s_%d", base, n)
		}
		used[key] = struct{}{}
		label := strings.TrimSpace(p.Label)
		if label == "" {
			label = strings.TrimSpace(p.Usage)
		}
		if label == "" {
			label = p.ID
		}
		list = append(list, namedParam{key: key, label: label})
		byToken[p.ID] = key
		byToken[key] = key
		for _, pr := range p.Props {
			if pr.Name == "alt-identifier" && pr.Value != "" {
				byToken[pr.Value] = key
			}
		}
	}
	return list, byToken
}

func statementPartOf(parts []part) *part {
	for i := range parts {
		if parts[i].Name == "statement" {
			return &parts[i]
		}
	}
	return nil
}

func flattenParts(items []part, chain []string, sortID string, rewrite func(string) string) []statementPart {
	var out []statementPart
	for _, item := range items {
		if item.Name != "" && item.Name != "item" {
			continue
		}
		label := propValue(item.Props, "label", "")
		id := partID(label, sortID, chain)
		prose := strings.TrimSpace(rewrite(item.Prose))
		if prose != "" {
			out = append(out, statementPart{id: id, statement: prose})
		}
		out = append(out, flattenParts(item.Parts, append(chain, id), sortID, rewrite)...)
	}
	return out
}

func partID(label, sortID string, chain []string) string {
	label = strings.TrimSpace(label)
	if sortID != "" {
		trimmed := label
		for _, prefix := range []string{"SR-" + sortID + ".", "SR-" + sortID, sortID + ".", sortID} {
			if strings.HasPrefix(strings.ToUpper(trimmed), strings.ToUpper(prefix)) && len(trimmed) > len(prefix) {
				rest := strings.TrimPrefix(trimmed[len(prefix):], ".")
				// len(prefix) is byte length; labels are ASCII.
				rest = strings.Trim(rest, ".")
				if rest != "" {
					return strings.ToLower(rest)
				}
			}
		}
	}
	local := strings.TrimSpace(label)
	local = strings.TrimSuffix(local, ".")
	if strings.HasPrefix(local, "(") && strings.HasSuffix(local, ")") && len(local) >= 2 {
		local = local[1 : len(local)-1]
	}
	local = strings.ToLower(strings.TrimSpace(local))
	if local == "" {
		local = "part"
	}
	if len(chain) == 0 {
		return local
	}
	return chain[len(chain)-1] + "." + local
}

func citations(links []link, resources map[string]resource, publisher string, resolve *Index) []externalRef {
	var out []externalRef
	seen := map[string]struct{}{}
	for _, lk := range links {
		if lk.Rel != "reference" {
			continue
		}
		res, ok := resources[strings.TrimPrefix(lk.Href, "#")]
		if !ok || res.Title == "" {
			continue
		}
		if controlRefRE.MatchString(res.Title) && resolve != nil {
			continue
		}
		url := ""
		if len(res.Rlinks) > 0 {
			url = res.Rlinks[0].Href
		}
		key := res.Title + "\n" + url
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, externalRef{
			source:      citationSource(res.Title, publisher),
			description: res.Title,
			url:         url,
		})
	}
	return out
}

func citationSource(title, publisher string) string {
	upper := strings.ToUpper(title)
	switch {
	case strings.Contains(upper, "CFR"):
		return "CFR"
	case strings.HasPrefix(upper, "FIPS"), strings.HasPrefix(upper, "SP "), strings.HasPrefix(upper, "IR "), strings.HasPrefix(upper, "NIST"):
		return "NIST"
	default:
		return publisher
	}
}

func mappingsFor(r requirement, self *Index, resolve *Index, resources map[string]resource, families map[string]string) ([]mapping, []externalRef, error) {
	var out []mapping
	var extra []externalRef
	for _, lk := range r.links {
		switch lk.Rel {
		case "related", "required", "reference":
			if lk.Rel != "reference" {
				continue
			}
			res, ok := resources[strings.TrimPrefix(lk.Href, "#")]
			if !ok || resolve == nil || !controlRefRE.MatchString(res.Title) {
				continue
			}
			target, ok := resolve.byZeroPadded[res.Title]
			if !ok {
				return nil, nil, fmt.Errorf("%s references %s, which is not in %s", r.id, res.Title, resolve.FrameworkID)
			}
			out = append(out, newMapping(r, target.id, "", "intersects-with",
				"Imported from an OSCAL reference link. NIST cites this SP 800-53 control from the requirement. The set relationship is unreviewed."))
		case "incorporated-into", "incorporated_into":
			target, part, family, err := resolveHref(lk.Href, self, families)
			if err != nil {
				return nil, nil, fmt.Errorf("%s: %w", r.id, err)
			}
			if family != "" {
				extra = append(extra, familyRef(lk.Rel, family))
				continue
			}
			out = append(out, newMapping(r, target, part, "subset-of",
				"Imported from an OSCAL incorporated-into link. NIST records the source requirement as incorporated into the target."))
		case "moved-to":
			target, part, family, err := resolveHref(lk.Href, self, families)
			if err != nil {
				return nil, nil, fmt.Errorf("%s: %w", r.id, err)
			}
			if family != "" {
				extra = append(extra, familyRef(lk.Rel, family))
				continue
			}
			out = append(out, newMapping(r, target, part, "equivalent-to",
				"Imported from an OSCAL moved-to link. NIST records the source requirement as moved to the target."))
		case "addressed_by":
			target, part, family, err := resolveHref(lk.Href, self, families)
			if err != nil {
				return nil, nil, fmt.Errorf("%s: %w", r.id, err)
			}
			if family != "" {
				extra = append(extra, familyRef(lk.Rel, family))
				continue
			}
			out = append(out, newMapping(r, target, part, "intersects-with",
				"Imported from an OSCAL addressed-by link. NIST records the source requirement as addressed by the target."))
		}
	}
	return out, extra, nil
}

func familyRef(rel, title string) externalRef {
	return externalRef{
		source:      "NIST",
		description: fmt.Sprintf("OSCAL %s link points at the %s family rather than a single requirement.", rel, title),
	}
}

func newMapping(r requirement, targetID, part, relationship, summary string) mapping {
	targetRef := targetID
	idRest := strings.TrimPrefix(r.id, "requirement--") + "_to_" + strings.TrimPrefix(targetID, "requirement--")
	if part != "" {
		targetRef = targetID + "#" + part
		idRest += "_part_" + strings.ReplaceAll(part, ".", "-")
	}
	return mapping{
		id:           "mapping--" + idRest,
		created:      r.created,
		modified:     r.modified,
		sourceRef:    r.id,
		targetRef:    targetRef,
		relationship: relationship,
		summary:      summary,
	}
}

func resolveHref(href string, idx *Index, families map[string]string) (string, string, string, error) {
	if m := partHrefRE.FindStringSubmatch(href); m != nil {
		target, ok := idx.byOscalID[m[1]]
		if !ok {
			return "", "", "", fmt.Errorf("link %s does not match a control", href)
		}
		if _, ok := target.parts[m[2]]; !ok {
			return "", "", "", fmt.Errorf("link %s does not match a statement part", href)
		}
		return target.id, m[2], "", nil
	}
	if m := hashHrefRE.FindStringSubmatch(href); m != nil {
		if target, ok := idx.byOscalID[m[1]]; ok {
			return target.id, "", "", nil
		}
		if title, ok := families[m[1]]; ok {
			if title == "" {
				title = strings.ToUpper(m[1])
			}
			return "", "", title, nil
		}
		return "", "", "", fmt.Errorf("link %s does not match a control", href)
	}
	bare := strings.TrimPrefix(href, "#")
	if target, ok := idx.bySortID[bare]; ok {
		return target.id, "", "", nil
	}
	if target, ok := idx.byOscalID[bare]; ok {
		return target.id, "", "", nil
	}
	return "", "", "", fmt.Errorf("link %s does not match a control", href)
}

func indexOf(frameworkID string, reqs []requirement) *Index {
	idx := &Index{
		FrameworkID:  frameworkID,
		byOscalID:    map[string]ref{},
		bySortID:     map[string]ref{},
		byZeroPadded: map[string]ref{},
	}
	for _, r := range reqs {
		item := ref{id: r.id, parts: map[string]struct{}{}}
		for _, p := range r.parts {
			item.parts[p.id] = struct{}{}
		}
		idx.byOscalID[r.oscalID] = item
		if r.sortID != "" {
			idx.bySortID[r.sortID] = item
		}
		if r.zeroPad != "" {
			idx.byZeroPadded[r.zeroPad] = item
		}
	}
	return idx
}

func writeLibrary(opt Options, stamp string, reqs []requirement, maps []mapping) error {
	reqDir := filepath.Join(opt.OutDir, "requirement", opt.FrameworkID)
	if err := os.RemoveAll(reqDir); err != nil {
		return err
	}
	if err := os.MkdirAll(reqDir, 0o755); err != nil {
		return err
	}
	fwDir := filepath.Join(opt.OutDir, "framework")
	mapDir := filepath.Join(opt.OutDir, "mapping")
	if err := os.MkdirAll(fwDir, 0o755); err != nil {
		return err
	}
	if err := os.MkdirAll(mapDir, 0o755); err != nil {
		return err
	}
	if err := removeOwnedMappings(mapDir, opt.FrameworkID); err != nil {
		return err
	}
	fw := renderFramework(opt.Name, opt.FrameworkID, stamp, stamp, opt.Version, opt.Publisher, opt.SourceURI, opt.SourcePath, opt.Commit)
	if err := os.WriteFile(filepath.Join(fwDir, opt.FrameworkID+".yaml"), []byte("# "+generatedComment+"\n"+fw), 0o644); err != nil {
		return err
	}
	for _, r := range reqs {
		body := "# " + generatedComment + "\n" + renderRequirement(r)
		if err := os.WriteFile(filepath.Join(reqDir, r.localSlug+".yaml"), []byte(body), 0o644); err != nil {
			return err
		}
	}
	for _, m := range maps {
		name := strings.TrimPrefix(m.id, "mapping--") + ".yaml"
		body := "# " + generatedComment + "\n" + renderMapping(m)
		if err := os.WriteFile(filepath.Join(mapDir, name), []byte(body), 0o644); err != nil {
			return err
		}
	}
	return nil
}

func removeOwnedMappings(dir, frameworkID string) error {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	prefix := frameworkID + "-"
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		if strings.HasPrefix(e.Name(), prefix) && strings.HasSuffix(e.Name(), ".yaml") {
			if err := os.Remove(filepath.Join(dir, e.Name())); err != nil {
				return err
			}
		}
	}
	return nil
}

func catalogTime(raw string) (string, error) {
	if raw == "" {
		return "", fmt.Errorf("catalog metadata last-modified is empty")
	}
	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		// NIST writes 2026-10-22T11:30:00.00000-00:00, which is not RFC3339
		// (five fractional digits). Trim the fraction and try again.
		trimmed := raw
		if i := strings.IndexByte(raw, '.'); i >= 0 {
			end := strings.IndexAny(raw[i:], "Z+-")
			if end > 0 {
				trimmed = raw[:i] + raw[i+end:]
			}
		}
		parsed, err = time.Parse(time.RFC3339, trimmed)
		if err != nil {
			return "", fmt.Errorf("catalog last-modified %q: %w", raw, err)
		}
	}
	return parsed.UTC().Format(time.RFC3339), nil
}

func propValue(props []prop, name, class string) string {
	var fallback string
	for _, p := range props {
		if p.Name != name {
			continue
		}
		if class == "" && p.Class == "" {
			return p.Value
		}
		if class != "" && p.Class == class {
			return p.Value
		}
		if fallback == "" && class == "" {
			fallback = p.Value
		}
	}
	if class == "" {
		return fallback
	}
	return ""
}

func displayID(props []prop, sortID, oscalID string) string {
	if v := unlabeledLabel(props); controlDisplayRE.MatchString(v) {
		return v
	}
	if sortID != "" {
		return sortID
	}
	if v := propValue(props, "label", "zero-padded"); v != "" {
		return v
	}
	if v := unlabeledLabel(props); v != "" {
		return v
	}
	return oscalID
}

func unlabeledLabel(props []prop) string {
	for _, p := range props {
		if p.Name == "label" && p.Class == "" {
			return p.Value
		}
	}
	return ""
}

func slug(s string) string {
	var b strings.Builder
	prev := false
	for _, r := range strings.ToLower(s) {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
			prev = false
			continue
		}
		if !prev {
			b.WriteByte('-')
			prev = true
		}
	}
	return strings.Trim(b.String(), "-")
}

func paramKey(id string) string {
	var b strings.Builder
	prev := false
	for _, r := range strings.ToLower(id) {
		if (r >= 'a' && r <= 'z') || unicode.IsDigit(r) {
			b.WriteRune(r)
			prev = false
			continue
		}
		if !prev {
			b.WriteByte('_')
			prev = true
		}
	}
	return strings.Trim(b.String(), "_")
}
