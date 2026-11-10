package oscalimport

// OSCALContentCommit is the usnistgov/oscal-content revision these URLs pin.
const OSCALContentCommit = "f0de6d8d8c059d374f15e0ae07508d82e370fc1d"

const oscalContentRaw = "https://raw.githubusercontent.com/usnistgov/oscal-content/" + OSCALContentCommit + "/"

// NISTCatalog is one official catalog the importer knows how to fetch.
type NISTCatalog struct {
	Options
	URL string
}

// NISTCatalogs returns SP 800-53 Rev 5 and SP 800-171 Rev 3, in that order.
// The 800-171 entry names 800-53 as its resolve target. The caller fills Resolve
// with the index returned from importing 800-53.
func NISTCatalogs() []NISTCatalog {
	return []NISTCatalog{
		{
			URL: oscalContentRaw + "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
			Options: Options{
				FrameworkID: "nist-sp-800-53-r5",
				Name:        "NIST SP 800-53 Revision 5",
				Publisher:   "NIST",
				SourceURI:   "https://github.com/usnistgov/oscal-content",
				SourcePath:  "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
				Commit:      OSCALContentCommit,
			},
		},
		{
			URL: oscalContentRaw + "nist.gov/SP800-171/rev3/json/NIST_SP800-171_rev3_catalog.json",
			Options: Options{
				FrameworkID: "nist-sp-800-171-r3",
				Name:        "NIST SP 800-171 Revision 3",
				Publisher:   "NIST",
				SourceURI:   "https://github.com/usnistgov/oscal-content",
				SourcePath:  "nist.gov/SP800-171/rev3/json/NIST_SP800-171_rev3_catalog.json",
				Commit:      OSCALContentCommit,
			},
		},
	}
}
