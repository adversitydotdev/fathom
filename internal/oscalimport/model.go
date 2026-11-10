package oscalimport

type catalogDoc struct {
	Catalog catalog `json:"catalog"`
}

type catalog struct {
	Metadata   metadata   `json:"metadata"`
	Groups     []group    `json:"groups"`
	BackMatter backMatter `json:"back-matter"`
}

type metadata struct {
	Title        string `json:"title"`
	LastModified string `json:"last-modified"`
	Version      string `json:"version"`
	OSCALVersion string `json:"oscal-version"`
}

type group struct {
	ID       string    `json:"id"`
	Title    string    `json:"title"`
	Controls []control `json:"controls"`
}

type control struct {
	ID       string    `json:"id"`
	Class    string    `json:"class"`
	Title    string    `json:"title"`
	Params   []param   `json:"params"`
	Props    []prop    `json:"props"`
	Links    []link    `json:"links"`
	Parts    []part    `json:"parts"`
	Controls []control `json:"controls"`
}

type param struct {
	ID    string `json:"id"`
	Label string `json:"label"`
	Usage string `json:"usage"`
	Props []prop `json:"props"`
}

type prop struct {
	Name  string `json:"name"`
	Value string `json:"value"`
	Class string `json:"class"`
}

type link struct {
	Href string `json:"href"`
	Rel  string `json:"rel"`
}

type part struct {
	ID    string `json:"id"`
	Name  string `json:"name"`
	Prose string `json:"prose"`
	Props []prop `json:"props"`
	Parts []part `json:"parts"`
}

type backMatter struct {
	Resources []resource `json:"resources"`
}

type resource struct {
	UUID   string `json:"uuid"`
	Title  string `json:"title"`
	Rlinks []struct {
		Href string `json:"href"`
	} `json:"rlinks"`
}

type requirement struct {
	id         string
	localSlug  string
	oscalID    string
	sortID     string
	zeroPad    string
	created    string
	modified   string
	displayID  string
	name       string
	framework  string
	class      string
	withdrawn  bool
	statement  string
	parameters []namedParam
	parts      []statementPart
	external   []externalRef
	links      []link
}

type namedParam struct {
	key   string
	label string
}

// tokenParam binds an OSCAL parameter id to the key written into prose.
type tokenParam struct {
	token string
	key   string
	label string
}

type statementPart struct {
	id        string
	statement string
}

type externalRef struct {
	source      string
	description string
	url         string
}

type mapping struct {
	id           string
	created      string
	modified     string
	sourceRef    string
	targetRef    string
	relationship string
	summary      string
}

type ref struct {
	id    string
	parts map[string]struct{}
}

// Index resolves OSCAL control identifiers to OpenGRC requirement ids.
type Index struct {
	FrameworkID  string
	byOscalID    map[string]ref
	bySortID     map[string]ref
	byZeroPadded map[string]ref
}
