# Remote FITS/ZIP Streaming Connector

This connector is a generic astronomy data-acquisition template for projects where large raw observation products remain in a remote instrument archive or server workspace. It converts a user-provided event/source table into a normalized manifest, inspects ZIP/FITS product availability without full extraction, selects dense observation windows, and defines the compact local tables expected by Draftpaper-loop.

The public template deliberately does not include private server addresses, user names, passwords, raw product roots, project-specific source lists, or real event identifiers. Project-specific scripts generated from this template should live under a paper project's `data/scripts/` directory and should write only processed tables, provenance records, parse-status reports, and quality summaries back into the local Draftpaper-loop project.
