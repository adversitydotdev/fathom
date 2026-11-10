package main

import (
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"opengrc/internal/oscalimport"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "ogrc: %v\n", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 {
		usage()
		return fmt.Errorf("a command is required")
	}
	switch args[0] {
	case "import":
		return runImport(args[1:])
	case "-h", "--help", "help":
		usage()
		return nil
	default:
		usage()
		return fmt.Errorf("unknown command %q", args[0])
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, `Usage:
  ogrc import nist --out library
  ogrc import oscal --catalog catalog.json --framework-id nist-sp-800-53-r5 --out library

import nist reads the pinned NIST OSCAL catalogs for SP 800-53 Rev 5 and
SP 800-171 Rev 3 and writes framework, requirement, and draft mapping files.

import oscal reads one OSCAL catalog from a file. Pass --resolve-catalog and
--resolve-framework when the catalog's reference links cite another framework
by zero-padded control label, the way SP 800-171 cites SP 800-53.
`)
}

func runImport(args []string) error {
	if len(args) == 0 {
		usage()
		return fmt.Errorf("import needs nist or oscal")
	}
	switch args[0] {
	case "nist":
		return importNIST(args[1:])
	case "oscal":
		return importOSCAL(args[1:])
	default:
		usage()
		return fmt.Errorf("unknown import target %q", args[0])
	}
}

func importNIST(args []string) error {
	fs := flag.NewFlagSet("import nist", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	out := fs.String("out", "library", "directory for the generated library")
	if err := fs.Parse(args); err != nil {
		return err
	}
	var resolve *oscalimport.Index
	var newest string
	for _, cat := range oscalimport.NISTCatalogs() {
		body, err := fetch(cat.URL)
		if err != nil {
			return err
		}
		cat.OutDir = *out
		cat.Resolve = resolve
		result, err := oscalimport.Import(body, cat.Options)
		if err != nil {
			return err
		}
		if cat.FrameworkID == "nist-sp-800-53-r5" {
			resolve = result.Index
		}
		if result.Modified > newest {
			newest = result.Modified
		}
		fmt.Printf("%s: %d requirements (%d withdrawn), %d mappings\n", result.FrameworkID, result.Requirements, result.Withdrawn, result.Mappings)
	}
	if err := oscalimport.WriteBundle(*out, newest, newest); err != nil {
		return err
	}
	return nil
}

func importOSCAL(args []string) error {
	fs := flag.NewFlagSet("import oscal", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	catalog := fs.String("catalog", "", "path to an OSCAL catalog JSON file")
	frameworkID := fs.String("framework-id", "", "OpenGRC framework id, such as nist-sp-800-53-r5")
	name := fs.String("name", "", "framework title; defaults to the catalog title")
	publisher := fs.String("publisher", "NIST", "publisher stored on the framework")
	out := fs.String("out", "library", "directory for the generated library")
	sourceURI := fs.String("source-uri", "", "upstream repository URI")
	sourcePath := fs.String("source-path", "", "path of the catalog inside the upstream repository")
	commit := fs.String("commit", "", "upstream commit the catalog was read from")
	resolveCatalog := fs.String("resolve-catalog", "", "OSCAL catalog whose control labels resolve reference links")
	resolveFramework := fs.String("resolve-framework", "", "framework id of --resolve-catalog")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *catalog == "" || *frameworkID == "" {
		return fmt.Errorf("--catalog and --framework-id are required")
	}
	body, err := os.ReadFile(*catalog)
	if err != nil {
		return err
	}
	opt := oscalimport.Options{
		FrameworkID: *frameworkID,
		Name:        *name,
		Publisher:   *publisher,
		SourceURI:   *sourceURI,
		SourcePath:  *sourcePath,
		Commit:      *commit,
		OutDir:      *out,
	}
	if *resolveCatalog != "" {
		if *resolveFramework == "" {
			return fmt.Errorf("--resolve-framework is required with --resolve-catalog")
		}
		raw, err := os.ReadFile(*resolveCatalog)
		if err != nil {
			return err
		}
		idx, err := oscalimport.IndexOnly(raw, *resolveFramework)
		if err != nil {
			return err
		}
		opt.Resolve = idx
	}
	result, err := oscalimport.Import(body, opt)
	if err != nil {
		return err
	}
	fmt.Printf("%s: %d requirements (%d withdrawn), %d mappings\n", result.FrameworkID, result.Requirements, result.Withdrawn, result.Mappings)
	return nil
}

func fetch(url string) ([]byte, error) {
	client := &http.Client{Timeout: 2 * time.Minute}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET %s: %s", url, resp.Status)
	}
	return io.ReadAll(resp.Body)
}
