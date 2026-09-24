**`etl-arc-ampe` now warns when an optional column is missing from the
workbook header, and refuses to overwrite a catalog whose guidance, related
controls or family it would empty.** The loader finds each column by its
exact caption. Before this change, a caption CMS rewords (`&` spelled `and`,
or `Related Controls` spelled `Related Control(s)`) did not fail the parse:
the sheet still qualified, all 215 controls were read, and every row read the
column as empty. The shipped catalog would have lost its 306 guidance entries
or its 210 related-control lists in a file that still loaded normally. The
parse report now starts with a `WARNING` line naming each missing column and
counts the controls that list related controls. The write is refused whenever
any of the three counts would fall below the catalog being replaced, and that
includes a partial drop as well as a total one. **If a new ARC-AMPE revision
really does remove content, move the existing catalog aside and re-run;** the
command otherwise exits non-zero.
