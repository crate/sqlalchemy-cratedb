from crate.theme.rtd.conf.sqlalchemy_cratedb import *  # noqa: F403

# Fallback guards, when parent theme does not introduce them.
if "html_theme_options" not in globals():
    html_theme_options = {}
if "intersphinx_mapping" not in globals():
    intersphinx_mapping = {}

# Re-configure sitemap generation URLs.
# This is a project without versioning.
sitemap_url_scheme = "{link}"

# Disable version chooser.
html_context.update(  # noqa: F405
    {
        "display_version": False,
        "current_version": None,
        "versions": [],
    }
)

intersphinx_mapping.update(
    {
        "py": ("https://docs.python.org/3/", None),
        "sa": ("https://docs.sqlalchemy.org/en/20/", None),
        "dask": ("https://docs.dask.org/en/stable/", None),
        "pandas": ("https://pandas.pydata.org/docs/", None),
    }
)

linkcheck_anchors = True
linkcheck_ignore = [
    r"https://github.com/crate/cratedb-examples/blob/main/by-language/python-sqlalchemy/.*",
    r"https://realpython.com/",
]

rst_prolog = """
.. |nbsp| unicode:: 0xA0
   :trim:
"""
