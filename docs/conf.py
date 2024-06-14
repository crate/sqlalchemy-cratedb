from crate.theme.rtd.conf.sqlalchemy_cratedb import *


if "intersphinx_mapping" not in globals():
    intersphinx_mapping = {}


intersphinx_mapping.update({
    'py': ('https://docs.python.org/3/', None),
    'sa': ('https://docs.sqlalchemy.org/en/20/', None),
    'dask': ('https://docs.dask.org/en/stable/', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    })


linkcheck_anchors = True
linkcheck_ignore = [r"https://github.com/crate/cratedb-examples/blob/main/by-language/python-sqlalchemy/.*"]


rst_prolog = """
.. |nbsp| unicode:: 0xA0
   :trim:
"""
