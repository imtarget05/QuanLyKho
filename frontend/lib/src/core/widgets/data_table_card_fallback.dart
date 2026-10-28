import 'package:flutter/material.dart';

/// Renders tabular data as labeled cards on narrow screens and a DataTable
/// when there is enough horizontal space.
class DataTableCardFallback extends StatelessWidget {
  const DataTableCardFallback({
    super.key,
    required this.columns,
    required this.rows,
    this.compactBreakpoint = 600,
    this.headingColor,
  });

  final List<DataColumn> columns;
  final List<DataRow> rows;
  final double compactBreakpoint;
  final Color? headingColor;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= compactBreakpoint) {
          return SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              headingRowColor: WidgetStatePropertyAll(headingColor),
              columns: columns,
              rows: rows,
            ),
          );
        }
        return Column(
          children: [
            for (final row in rows)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (var i = 0; i < columns.length; i++)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SizedBox(
                                width: 112,
                                child: DefaultTextStyle.merge(
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelMedium!
                                      .copyWith(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurfaceVariant,
                                      ),
                                  child: columns[i].label,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(child: row.cells[i].child),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}
