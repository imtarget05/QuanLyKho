import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import '../../app/app_shell.dart';
import '../../data/repositories/http_bankops_repository.dart';
import '../auth/auth_service.dart';

/// "Khai" là trợ lý cho ứng dụng Quản Lý Kho Trà Sữa.
/// is intentionally not shown inside a user's conversation.
class AiAssistantDialog extends StatefulWidget {
  const AiAssistantDialog({super.key});

  static Future<void> show(BuildContext context) {
    final repo = RepositoryScope.maybeOf(context);
    final theme = Theme.of(context);
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: false,
      backgroundColor: Colors.transparent,
      elevation: 0,
      builder: (_) {
        Widget child = const AiAssistantDialog();
        if (repo != null) {
          child = RepositoryScope(repository: repo, child: child);
        }
        return Theme(
          data: theme.copyWith(
            bottomSheetTheme: theme.bottomSheetTheme.copyWith(
              showDragHandle: false,
            ),
          ),
          child: child,
        );
      },
    );
  }

  @override
  State<AiAssistantDialog> createState() => _AiAssistantDialogState();
}

class _ChatMessage {
  const _ChatMessage({
    required this.isUser,
    required this.text,
    this.needsSignIn = false,
  });

  final bool isUser;
  final String text;
  final bool needsSignIn;
}

class _ChatRequestFailure implements Exception {
  const _ChatRequestFailure(this.statusCode);
  final int statusCode;
}

String _shortSourceLabel(Map source) {
  final raw = (source['source'] ?? '').toString();
  var name = raw.split('/').last;
  if (name.endsWith('.md')) {
    name = name.substring(0, name.length - 3);
  }
  return name.trim();
}

class _AiAssistantDialogState extends State<AiAssistantDialog> {
  static const _brand = Color(0xFF153E75);
  static const _ink = Color(0xFF10233F);
  static const _muted = Color(0xFF60708A);

  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final List<_ChatMessage> _messages = [];
  bool _isLoading = false;
  bool _disposed = false;

  final List<String> _quickPrompts = const [
    'Ai được lập và duyệt phiếu kho?',
    'Chốt ca sáng/chiều theo công thức nào?',
    'Tồn chạm Min hoặc lệch kiểm kê thì xử lý sao?',
    'Lô sữa tươi cận date cần làm gì?',
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_messages.isNotEmpty) return;
    final user =
        SessionScope.maybeOf(context)?.user ?? context.read<AuthService>().user;
    final name = (user?.displayName.trim().isNotEmpty ?? false)
        ? user!.displayName.trim()
        : (user?.username.trim().isNotEmpty ?? false)
            ? user!.username.trim()
            : 'bạn';
    _messages.add(_ChatMessage(isUser: false, text: 'Xin chào, $name.'));
  }

  Future<void> _sendMessage(String text) async {
    final query = text.trim();
    if (query.isEmpty || _isLoading) return;
    _controller.clear();
    setState(() {
      _messages.add(_ChatMessage(isUser: true, text: query));
      _messages.add(const _ChatMessage(isUser: false, text: 'Đang trả lời…'));
      _isLoading = true;
    });
    final responseIndex = _messages.length - 1;
    _scrollToBottom();

    String answer = '';
    final sources = <String>[];
    var needsSignIn = false;
    try {
      final repository = RepositoryScope.maybeOf(context);
      final auth = context.read<AuthService>();
      final isOffline =
          auth.isOfflineSession || repository is! HttpBankOpsRepository;
      if (isOffline) {
        final localSop = _getLocalSopAnswer(query);
        answer = localSop ??
            '📌 **Quy chuẩn vận hành**: Khai đang hoạt động ở chế độ ngoại tuyến (Offline Demo). Mọi thao tác kho được lưu trữ an toàn trên thiết bị của bạn.';
        return;
      }

      final token = await repository.accessToken;
      if (token == null || token.isEmpty) {
        final localSop = _getLocalSopAnswer(query);
        if (localSop != null) {
          answer = localSop;
          return;
        }
        throw const _ChatRequestFailure(401);
      }
      final apiBaseUrl = repository.baseUrl;
      final request =
          http.Request('POST', Uri.parse('$apiBaseUrl/ai/chat/stream'))
            ..headers.addAll({
              'Content-Type': 'application/json',
              'Accept': 'text/event-stream',
              'Authorization': 'Bearer $token',
            })
            ..body = json.encode({'message': query});

      final client = http.Client();
      try {
        try {
          final response =
              await client.send(request).timeout(const Duration(seconds: 25));
          if (response.statusCode != 200) {
            throw _ChatRequestFailure(response.statusCode);
          }
          String event = '';
          await for (final line in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
            if (line.startsWith('event: ')) {
              event = line.substring(7).trim();
            } else if (line.startsWith('data: ')) {
              final raw = line.substring(6).trim();
              if (raw.isEmpty) continue;
              final data = json.decode(raw);
              if (event == 'delta' && data is Map && data['text'] is String) {
                answer += data['text'] as String;
                if (mounted && !_disposed) {
                  setState(() => _messages[responseIndex] =
                      _ChatMessage(isUser: false, text: answer));
                  _scrollToBottom();
                }
              } else if (event == 'sources' && data is List) {
                sources.addAll(data
                    .whereType<Map>()
                    .map(_shortSourceLabel)
                    .where((source) => source.trim().isNotEmpty));
              } else if (event == 'error') {
                throw const _ChatRequestFailure(503);
              }
            }
          }
        } on _ChatRequestFailure {
          rethrow;
        } catch (_) {
          // Fall back only for an SSE transport failure, never after 401/403/429.
          final response = await http
              .post(
                Uri.parse('$apiBaseUrl/ai/chat'),
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': 'Bearer $token'
                },
                body: json.encode({'message': query}),
              )
              .timeout(const Duration(seconds: 25));
          if (response.statusCode != 200) {
            throw _ChatRequestFailure(response.statusCode);
          }
          final data = json.decode(utf8.decode(response.bodyBytes));
          if (data is! Map) {
            throw const _ChatRequestFailure(503);
          }
          if (data['chunks'] is List) {
            final chunks = (data['chunks'] as List)
                .whereType<Map>()
                .map((c) => c['chunk'] as String?)
                .whereType<String>()
                .where((s) => s.isNotEmpty);
            answer = chunks.join('\n\n');
          } else if (data['answer'] is String) {
            answer = data['answer'] as String;
          } else {
            throw const _ChatRequestFailure(503);
          }
          if (data['sources'] is List) {
            sources.addAll((data['sources'] as List)
                .whereType<Map>()
                .map(_shortSourceLabel)
                .where((source) => source.trim().isNotEmpty));
          }
        }
      } finally {
        client.close();
      }
      if (answer.isEmpty) throw const _ChatRequestFailure(503);
      final briefSources = <String>[];
      for (final source in sources) {
        if (source.isEmpty || briefSources.contains(source)) continue;
        briefSources.add(source);
        if (briefSources.length == 3) break;
      }
      if (briefSources.isNotEmpty) {
        answer += "\n\nNguồn: ${briefSources.join(', ')}";
      }
      if (answer.trim().contains('Chưa tìm thấy thông tin') || answer.isEmpty) {
        final localSop = _getLocalSopAnswer(query);
        if (localSop != null) answer = localSop;
      }
    } on _ChatRequestFailure catch (error) {
      final localSop = _getLocalSopAnswer(query);
      if (localSop != null && error.statusCode != 401) {
        answer = localSop;
      } else if (error.statusCode == 401) {
        answer = 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.';
        needsSignIn = true;
      } else if (error.statusCode == 403) {
        answer = 'Tài khoản này chưa được phép dùng trợ lý nghiệp vụ.';
      } else if (error.statusCode == 429) {
        answer = 'Bạn đã gửi quá nhiều câu hỏi. Hãy thử lại sau một phút.';
      } else if (error.statusCode == 503) {
        answer = localSop ?? 'Khai chưa sẵn sàng. Vui lòng thử lại sau.';
      } else {
        answer = localSop ?? 'Máy chủ trả lỗi ${error.statusCode}.';
      }
    } catch (_) {
      final localSop = _getLocalSopAnswer(query);
      answer = localSop ??
          'Không kết nối được với Khai. Hãy kiểm tra kết nối rồi thử lại.';
    } finally {
      if (mounted && !_disposed) {
        setState(() {
          if (answer.isNotEmpty) {
            _messages[responseIndex] = _ChatMessage(
              isUser: false,
              text: answer,
              needsSignIn: needsSignIn,
            );
          }
          _isLoading = false;
        });
        _scrollToBottom();
      }
    }
  }

  static String? _getLocalSopAnswer(String query) {
    final q = query.toLowerCase();
    if (q.contains('lập') ||
        q.contains('duyệt') ||
        q.contains('maker') ||
        q.contains('checker') ||
        q.contains('ai được')) {
      return '📌 **Quy trình áp dụng**: Phân quyền & Kiểm soát kép Dual Control (Maker - Checker SOP).\n\n'
          '👤 **Người lập (Maker)**: Nhân viên ca trực, Pha chế chính, Thủ kho (role `staff`/`maker`) có thẩm quyền tạo phiếu kho (nhập, xuất, điều chuyển, điều chỉnh).\n\n'
          '🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng (Store Manager), Kiểm soát viên, Admin (role `approver`/`admin`) kiểm tra thực tế và phê duyệt ghi sổ. Bắt buộc tuân thủ nguyên tắc `created_by != approved_by` (người tạo không được tự duyệt phiếu của chính mình).\n\n'
          '📑 **Căn cứ & Bằng chứng**: Mã phiếu kho (REQ/STK), biên bản giao nhận đủ 2 chữ ký Maker & Checker, mã xác thực Audit Stamp SHA-256 đối soát trên sổ cái.\n\n'
          'Nguồn: docs/05-workflows';
    }
    if (q.contains('chốt ca') ||
        q.contains('công thức') ||
        q.contains('bàn giao') ||
        q.contains('ca sáng') ||
        q.contains('ca chiều')) {
      return '📌 **Quy trình áp dụng**: Bàn giao ca trực & Kiểm đếm tồn quầy pha chế (Shift Handover SOP).\n\n'
          '📐 **Công thức tính toán**: `Tồn đầu ca + Nhập trong ca - Tiêu hao định mức theo đơn POS - Xuất hủy/hỏng = Tồn cuối ca lý thuyết`. So sánh đối chiếu với số lượng kiểm đếm thực tế.\n\n'
          '👤 **Người lập (Maker)**: Trưởng ca hiện tại lập phiếu kiểm đếm và biên bản bàn giao ca.\n\n'
          '🛡️ **Người duyệt (Checker)**: Trưởng ca tiếp nhận hoặc Quản lý ca trực kiểm tra đối chiếu và ký xác nhận.\n\n'
          '📑 **Căn cứ & Bằng chứng**: Báo cáo tổng kết ca từ máy POS, biên bản kiểm đếm két tiền và nguyên vật liệu có chữ ký xác nhận của cả 2 ca.\n\n'
          'Nguồn: docs/05-workflows';
    }
    if (q.contains('min') ||
        q.contains('lệch') ||
        q.contains('định mức') ||
        q.contains('kiểm kê')) {
      return '📌 **Quy trình áp dụng**: Quản trị an toàn tồn kho (Min/Max Safety Levels) & Xử lý sai lệch kiểm kê.\n\n'
          '⚠️ **Nguyên tắc xử lý**: Khi tồn khả dụng chạm ngưỡng Min, hệ thống kích hoạt cảnh báo lập phiếu nhập/chuyển kho bổ sung. Khi phát hiện chênh lệch kiểm kê (lệch ≥ 10 đơn vị hoặc giá trị lớn), xếp loại High Risk, lập tức đếm lại và giải trình nguyên nhân.\n\n'
          '👤 **Người lập (Maker)**: Trưởng ca lập biên bản giải trình chênh lệch và tạo phiếu điều chỉnh (Adjustment).\n\n'
          '🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng (Store Manager) hoặc Admin xem xét thực tế và duyệt phiếu.\n\n'
          '📑 **Căn cứ & Bằng chứng**: Phiếu kiểm kê kho (STK), biên bản giải trình nguyên nhân (đong hao hụt, đổ vỡ, lỗi pha chế), dấu kiểm toán hệ thống.\n\n'
          'Nguồn: docs/05-workflows';
    }
    if (q.contains('sữa') ||
        q.contains('cận date') ||
        q.contains('date') ||
        q.contains('hsd') ||
        q.contains('fefo')) {
      return '📌 **Quy trình áp dụng**: Nguyên tắc nhập trước xuất trước theo hạn sử dụng (FEFO - First Expired, First Out).\n\n'
          '🥛 **Quy định xử lý sữa tươi / nguyên liệu tươi**: Lô sữa tươi cận date (còn ≤ 24-48 giờ) phải dán tem cảnh báo màu cam và ưu tiên dùng ngay trong ca. Nếu đã quá hạn sử dụng, nghiêm cấm pha chế cho khách, phải lập phiếu xuất hủy (Disposal Request).\n\n'
          '👤 **Người lập (Maker)**: Nhân viên quầy phát hiện và lập phiếu đề xuất xuất hủy nguyên liệu cận/quá hạn.\n\n'
          '🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng kiểm tra thực tế tình trạng hàng hóa và ký duyệt tiêu hủy.\n\n'
          '📑 **Căn cứ & Bằng chứng**: Tem nhãn phụ lô hàng (Lot/Batch ID), mã HSD in trên bao bì nhà sản xuất, phiếu xuất hủy nguyên liệu có phê duyệt.\n\n'
          'Nguồn: docs/05-workflows';
    }
    return null;
  }

  Future<void> _signOutAndClose() async {
    await context.read<AuthService>().signOut();
    if (mounted) Navigator.of(context).pop();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final size = MediaQuery.of(context).size;
    final isCompact = size.width < 768;

    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: isCompact ? double.infinity : 680,
          maxHeight: size.height * 0.88,
        ),
        child: Container(
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF0F172A) : Colors.white,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.25),
                blurRadius: 24,
                offset: const Offset(0, -6),
              ),
            ],
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(children: [
            _buildDragHandle(),
            _buildHeader(),
            _buildQuickPrompts(),
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 8),
                itemCount: _messages.length,
                itemBuilder: (_, index) => _buildMessage(_messages[index]),
              ),
            ),
            _buildComposer(),
          ]),
        ),
      ),
    );
  }

  Widget _buildDragHandle() => Container(
        width: double.infinity,
        color: _ink,
        padding: const EdgeInsets.only(top: 8, bottom: 2),
        alignment: Alignment.center,
        child: Container(
          width: 38,
          height: 4,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.35),
            borderRadius: BorderRadius.circular(2),
          ),
        ),
      );

  Widget _buildHeader() => Container(
        padding: const EdgeInsets.fromLTRB(20, 16, 12, 16),
        color: _ink,
        child: Row(children: [
          Container(
            width: 42,
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: const Color(0xFF74D3C4),
              borderRadius: BorderRadius.circular(13),
            ),
            child: const Text('K',
                style: TextStyle(
                    color: _ink, fontSize: 23, fontWeight: FontWeight.w800)),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Khai',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 19,
                      fontWeight: FontWeight.w800)),
              SizedBox(height: 2),
              Text('Trợ lý Quản Lý Kho Trà Sữa',
                  style: TextStyle(color: Color(0xFFC3D4EE), fontSize: 12)),
            ]),
          ),
          IconButton(
            tooltip: 'Đóng trợ lý',
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.close_rounded, color: Colors.white),
          ),
        ]),
      );

  Widget _buildQuickPrompts() => Container(
        alignment: Alignment.centerLeft,
        color: const Color(0xFFF5F8FC),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: _quickPrompts
                .map((prompt) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ActionChip(
                        label: Text(prompt),
                        labelStyle: const TextStyle(fontSize: 12, color: _ink),
                        side: const BorderSide(color: Color(0xFFD8E2EF)),
                        backgroundColor: Colors.white,
                        onPressed:
                            _isLoading ? null : () => _sendMessage(prompt),
                      ),
                    ))
                .toList(),
          ),
        ),
      );

  Widget _buildMessage(_ChatMessage message) {
    final bubbleColor = message.isUser ? _brand : const Color(0xFFF1F5F9);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment:
            message.isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!message.isUser) ...[
            Container(
              width: 30,
              height: 30,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                  color: Color(0xFFD9F1EC), shape: BoxShape.circle),
              child: const Text('K',
                  style: TextStyle(color: _ink, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 9),
          ],
          Flexible(
            child: Container(
              constraints: const BoxConstraints(maxWidth: 570),
              padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
              decoration: BoxDecoration(
                color: bubbleColor,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(16),
                  topRight: const Radius.circular(16),
                  bottomLeft: Radius.circular(message.isUser ? 16 : 4),
                  bottomRight: Radius.circular(message.isUser ? 4 : 16),
                ),
              ),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildFormattedText(
                      message.text,
                      message.isUser ? Colors.white : _ink,
                    ),
                    if (message.needsSignIn) ...[
                      const SizedBox(height: 10),
                      OutlinedButton.icon(
                        onPressed: _signOutAndClose,
                        icon: const Icon(Icons.login_rounded, size: 16),
                        label: const Text('Đăng nhập lại'),
                        style:
                            OutlinedButton.styleFrom(foregroundColor: _brand),
                      ),
                    ],
                  ]),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFormattedText(String text, Color baseColor) {
    final blocks = text.split('\n\n')
        .map((block) => block.trim())
        .where((block) => block.isNotEmpty)
        .toList();
    final children = <Widget>[];
    for (int i = 0; i < blocks.length; i++) {
      if (i > 0) children.add(const SizedBox(height: 6));
      final block = blocks[i];
      if (block.startsWith('# ')) {
        children.add(
            _buildHeading(block.substring(2), baseColor, 16.0, FontWeight.w800));
      } else if (block.startsWith('## ')) {
        children.add(
            _buildHeading(block.substring(3), baseColor, 14.5, FontWeight.w700));
      } else if (block.startsWith('- ') || block.startsWith('\u2022 ')) {
        children.add(_buildBullet(block, baseColor));
      } else {
        children.add(_buildParagraph(block, baseColor));
      }
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: children,
    );
  }

  Widget _buildHeading(String text, Color baseColor, double fontSize,
      FontWeight weight) {
    final trimmed = text.trim();
    if (trimmed.contains('**')) {
      return RichText(
        text: TextSpan(
          style: TextStyle(color: baseColor, fontSize: fontSize, height: 1.48),
          children: _parseInlineSpans(trimmed, baseColor,
              fontSize: fontSize, weight: weight),
        ),
      );
    }
    return Text(
      trimmed,
      style: TextStyle(color: baseColor, fontSize: fontSize, fontWeight: weight),
    );
  }

  Widget _buildParagraph(String block, Color baseColor) {
    final lines = block.split('\n');
    final spans = <InlineSpan>[];
    for (int i = 0; i < lines.length; i++) {
      if (i > 0) spans.add(const TextSpan(text: '\n'));
      spans.addAll(_parseInlineSpans(lines[i], baseColor));
    }
    return RichText(text: TextSpan(children: spans));
  }

  Widget _buildBullet(String block, Color baseColor) {
    final content = block.substring(2).trim();
    final lines = content.split('\n');
    final spans = <InlineSpan>[];
    for (int i = 0; i < lines.length; i++) {
      if (i > 0) spans.add(const TextSpan(text: '\n'));
      if (i == 0) spans.add(const TextSpan(text: '\u2022 '));
      spans.addAll(_parseInlineSpans(lines[i], baseColor));
    }
    return RichText(
      text: TextSpan(
        style: TextStyle(color: baseColor, fontSize: 13.5, height: 1.48),
        children: spans,
      ),
    );
  }

  List<InlineSpan> _parseInlineSpans(String text, Color baseColor,
      {double fontSize = 13.5, FontWeight weight = FontWeight.w400}) {
    final spans = <InlineSpan>[];
    final parts = text.split('**');
    for (int i = 0; i < parts.length; i++) {
      if (parts[i].isEmpty) continue;
      final isBold = i % 2 == 1;
      spans.add(
        TextSpan(
          text: parts[i],
          style: TextStyle(
            color: baseColor,
            fontSize: fontSize,
            fontWeight: isBold ? FontWeight.w800 : weight,
            height: 1.48,
          ),
        ),
      );
    }
    return spans;
  }

  Widget _buildComposer() => Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 12, 14),
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: Color(0xFFE0E7F0))),
        ),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _controller,
              enabled: !_isLoading,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              decoration: InputDecoration(
                hintText: 'Hỏi về quy trình, tồn kho hoặc đối soát…',
                hintStyle: const TextStyle(color: _muted),
                filled: true,
                fillColor: const Color(0xFFF6F8FB),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFFD8E2EF)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFFD8E2EF)),
                ),
              ),
              onSubmitted: _isLoading ? null : _sendMessage,
            ),
          ),
          const SizedBox(width: 8),
          Semantics(
            label: 'Gửi câu hỏi',
            button: true,
            child: IconButton.filled(
              tooltip: 'Gửi câu hỏi',
              onPressed:
                  _isLoading ? null : () => _sendMessage(_controller.text),
              style: IconButton.styleFrom(
                  backgroundColor: _brand, minimumSize: const Size(48, 48)),
              icon: const Icon(Icons.arrow_upward_rounded),
            ),
          ),
        ]),
      );
}
