# Manufacturing code layout

This package contains the implementation shared by both Manufacturing views:

- `common.py`: XML discovery and read-only persisted-data loaders
- `config.py`: shared runtime configuration
- `workflow.py`: parsing, caching, status hydration, and view-bundle assembly
- `*_sections.py`: operation builders whose behavior is identical in both views

The view packages keep only their policy and presentation differences:

- `manufacturing`: default renderer, state writers, and merging CNC builder
- `manufacturing.admin`: admin renderer, display-data writers, and non-merging CNC builder

The small files left at the old import locations are compatibility adapters so
the application and operation modules retain their existing public imports.
