import 'package:flutter/material.dart';

/// 月份 + 日期两个联动下拉框，两端 `home/home_page.dart` 共用。
///
/// 选中的月/日、以及随月份变化的日期列表都由这个组件自己持有；调用方只通过
/// [onMonthChanged] / [onDayChanged] 拿到结果去发请求。提取前这段逻辑两端各
/// 一份且完全相同 —— 换 `find_dropdown` 和修闰年那两次，同一处改动都写了两遍。
class MonthDayPicker extends StatefulWidget {
  /// 推算每月天数用的年份。传各端查询用的那个年份，日期选择才和查询对得上
  /// （闰年 2 月 29 天）。
  final int year;

  /// 选定月份后回调，参数是 1–12。
  final ValueChanged<int> onMonthChanged;

  /// 选定日期后回调，参数是 (月, 日)。日期列表在选月之前是空的，所以这个回调
  /// 一定发生在 [onMonthChanged] 之后。
  final void Function(int month, int day) onDayChanged;

  const MonthDayPicker({
    Key? key,
    required this.year,
    required this.onMonthChanged,
    required this.onDayChanged,
  }) : super(key: key);

  @override
  State<MonthDayPicker> createState() => _MonthDayPickerState();
}

class _MonthDayPickerState extends State<MonthDayPicker> {
  static const List<String> _months = [
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
  ];

  String _month = "";
  String _day = "";
  List<String> _days = const [];

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        const Padding(padding: EdgeInsets.all(1)),
        Container(
          padding: const EdgeInsets.all(2),
          child: DropdownButton<String>(
            hint: const Text("请选择月份"),
            value: _month.isEmpty ? null : _month,
            items: _months
                .map((m) => DropdownMenuItem<String>(value: m, child: Text(m)))
                .toList(),
            onChanged: (item) {
              if (item == null) return;
              setState(() {
                _month = item;
                // 换月后旧的“日”可能越界（31 号 -> 30 天的月份），清掉，
                // 否则 DropdownButton 会因 value 不在 items 中而断言失败。
                _day = "";
                // 每月天数交给 DateTime 推算：DateTime(y, m+1, 0) 就是第 m
                // 个月的最后一天，闰年 2 月自动得 29。原先是手写 if 链，
                // 2 月恒为 28 天。
                final int daysInMonth = DateTime(
                  widget.year,
                  int.parse(item) + 1,
                  0,
                ).day;
                _days = [for (int i = 1; i <= daysInMonth; i++) i.toString()];
              });
              widget.onMonthChanged(int.parse(item));
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.all(2),
          child: DropdownButton<String>(
            hint: const Text("请选择日期"),
            value: _day.isEmpty ? null : _day,
            items: _days
                .map((d) => DropdownMenuItem<String>(value: d, child: Text(d)))
                .toList(),
            onChanged: (item) {
              if (item == null) return;
              setState(() {
                _day = item;
              });
              widget.onDayChanged(int.parse(_month), int.parse(item));
            },
          ),
        ),
        const Padding(padding: EdgeInsets.all(1)),
      ],
    );
  }
}
