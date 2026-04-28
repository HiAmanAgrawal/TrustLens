import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../providers/chat_provider.dart';
import '../../providers/scan_provider.dart';
import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/chat_bubble.dart';
import '../../widgets/dot_grid_background.dart';

/// AI Health Chat screen — full-screen chat interface.
/// Uses Riverpod chatProvider for real backend AI chat via /api/ai/chat.
class AiChatScreen extends ConsumerStatefulWidget {
  const AiChatScreen({super.key});

  @override
  ConsumerState<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends ConsumerState<AiChatScreen> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    // Defer provider mutation until after the first build completes.
    Future.microtask(() {
      if (!mounted) return;
      final scanState = ref.read(scanProvider);
      ref.read(chatProvider.notifier).initWithContext(scanState.result);
    });
  }

  void _sendMessage(String text) {
    if (text.trim().isEmpty) return;
    _messageController.clear();
    ref.read(chatProvider.notifier).sendMessage(text);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final chatState = ref.watch(chatProvider);

    // Auto-scroll when new messages arrive.
    ref.listen(chatProvider, (prev, next) {
      if (prev != null && next.messages.length > prev.messages.length) {
        _scrollToBottom();
      }
    });

    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            children: [
              _buildAppBar(context),
              _buildDisclaimer(),
              Expanded(
                child: ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  itemCount: chatState.messages.length + (chatState.isTyping ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == chatState.messages.length && chatState.isTyping) {
                      return const TypingIndicator();
                    }
                    final msg = chatState.messages[index];
                    return ChatBubble(
                      message: msg.content,
                      isUser: msg.isUser,
                      suggestions: msg.suggestions,
                      onSuggestionTap: (s) => _sendMessage(s),
                    );
                  },
                ),
              ),
              _buildInputBar(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppBar(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 8, 20, 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.muted, width: 1)),
      ),
      child: Row(
        children: [
          IconButton(
            onPressed: () => context.pop(),
            icon: const Icon(LucideIcons.arrowLeft, color: AppColors.onBackground),
            tooltip: 'Go back',
          ),
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: AppColors.surface,
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.border, width: 2),
            ),
            child: const Icon(LucideIcons.bot, size: 18, color: AppColors.secondary),
          ),
          const SizedBox(width: 10),
          Text(
            'AI Health Assistant',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: AppColors.onBackground,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDisclaimer() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      color: AppColors.cautionBadge.withValues(alpha: 0.08),
      child: Row(
        children: [
          const Icon(LucideIcons.info, size: 12, color: AppColors.cautionBadge),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'AI responses are for informational purposes only. Not medical advice.',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 12,
                color: AppColors.cautionBadge,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.muted, width: 1)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: WobblyBorders.input,
                border: Border.all(color: AppColors.border, width: 2),
              ),
              child: TextField(
                controller: _messageController,
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 16,
                  color: AppColors.onBackground,
                ),
                decoration: InputDecoration(
                  hintText: 'Ask a health question...',
                  hintStyle: GoogleFonts.plusJakartaSans(
                    fontSize: 16,
                    color: AppColors.onBackground.withValues(alpha: 0.4),
                  ),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                ),
                onSubmitted: _sendMessage,
                textInputAction: TextInputAction.send,
              ),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () => _sendMessage(_messageController.text),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: AppGradients.primary,
                shape: BoxShape.circle,
                boxShadow: const [AppShadows.buttonGlow],
              ),
              child: const Icon(LucideIcons.send, size: 18, color: AppColors.onPrimary),
            ),
          ),
        ],
      ),
    );
  }
}
