import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../../theme/app_theme.dart';
import '../../theme/wobbly_borders.dart';
import '../../widgets/chat_bubble.dart';
import '../../widgets/dot_grid_background.dart';

/// AI Health Chat screen — full-screen chat interface.
/// Supports scan context pre-loading and standalone health Q&A.
class AiChatScreen extends StatefulWidget {
  const AiChatScreen({super.key});

  @override
  State<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends State<AiChatScreen> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  bool _isTyping = false;

  // Mock conversation
  final List<_ChatMsg> _messages = [
    _ChatMsg(
      'I analyzed your scan. Here\'s what I found \u2014 feel free to ask me anything about it.\n\n'
      'Your Dolo-650 tablet (Batch: DOBS3975) has been verified against Micro Labs Limited\'s records. '
      'The match score is 8.5/10, which indicates a genuine product.',
      false,
      ['What about side effects?', 'Is it safe during pregnancy?', 'Any drug interactions?'],
    ),
  ];

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _sendMessage(String text) {
    if (text.trim().isEmpty) return;

    setState(() {
      _messages.add(_ChatMsg(text.trim(), true, null));
      _messageController.clear();
      _isTyping = true;
    });

    _scrollToBottom();

    // Simulate AI response after a delay
    Future.delayed(const Duration(milliseconds: 1500), () {
      if (!mounted) return;
      setState(() {
        _isTyping = false;
        _messages.add(_ChatMsg(
          _getMockResponse(text),
          false,
          ['Tell me more', 'What should I do?', 'Is this common?'],
        ));
      });
      _scrollToBottom();
    });
  }

  String _getMockResponse(String userMessage) {
    final lower = userMessage.toLowerCase();
    if (lower.contains('side effect')) {
      return 'Common side effects of Paracetamol (Dolo-650) include:\n\n'
          '\u2022 Nausea (in ~5% of users)\n'
          '\u2022 Mild stomach discomfort\n'
          '\u2022 Rarely, skin rash or allergic reactions\n\n'
          'Serious side effects are rare at recommended doses. However, exceeding 4g/day can cause '
          'liver damage. Always follow your doctor\'s prescribed dosage.\n\n'
          '\u26A0 This is not medical advice. Consult a qualified healthcare provider for medical decisions.';
    }
    if (lower.contains('pregnan')) {
      return 'Paracetamol is generally considered safe during pregnancy when taken at recommended doses. '
          'It is the preferred analgesic and antipyretic during all trimesters.\n\n'
          'However, recent studies suggest prolonged use may have some risks. Always consult your '
          'obstetrician before taking any medication during pregnancy.\n\n'
          '\u26A0 This is not medical advice. Consult a qualified healthcare provider for medical decisions.';
    }
    if (lower.contains('interaction')) {
      return 'Known interactions for Paracetamol:\n\n'
          '\u2022 Warfarin \u2014 may increase bleeding risk\n'
          '\u2022 Alcohol \u2014 increases liver toxicity risk\n'
          '\u2022 Isoniazid \u2014 may increase liver toxicity\n'
          '\u2022 Carbamazepine \u2014 may reduce efficacy\n\n'
          'Based on your profile, the caffeine in this formulation may mildly interact with your '
          'hypertension medication.\n\n'
          '\u26A0 This is not medical advice. Consult a qualified healthcare provider for medical decisions.';
    }
    return 'That\'s a great question. Based on the scan data and your health profile, '
        'I can tell you that this product appears to be safe for general use. However, '
        'I\'d recommend discussing any specific concerns with your healthcare provider, '
        'especially given your health conditions.\n\n'
        '\u26A0 This is not medical advice. Consult a qualified healthcare provider for medical decisions.';
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
    return Scaffold(
      backgroundColor: AppColors.background,
      body: DotGridBackground(
        child: SafeArea(
          child: Column(
            children: [
              // App bar
              _buildAppBar(context),
              // Disclaimer
              _buildDisclaimer(),
              // Messages
              Expanded(
                child: ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  itemCount: _messages.length + (_isTyping ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == _messages.length && _isTyping) {
                      return const TypingIndicator();
                    }
                    final msg = _messages[index];
                    return ChatBubble(
                      message: msg.text,
                      isUser: msg.isUser,
                      suggestions: msg.suggestions,
                      onSuggestionTap: (s) => _sendMessage(s),
                    );
                  },
                ),
              ),
              // Input bar
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
          // Bot avatar
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

class _ChatMsg {
  final String text;
  final bool isUser;
  final List<String>? suggestions;
  _ChatMsg(this.text, this.isUser, this.suggestions);
}
