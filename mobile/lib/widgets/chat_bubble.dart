import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_icons/lucide_icons.dart';

import '../theme/app_theme.dart';
import '../theme/wobbly_borders.dart';

/// Chat bubble widget — wobbly border, hard shadow.
/// User: red bg, right-aligned. AI: white bg + bot avatar, left-aligned.
class ChatBubble extends StatelessWidget {
  final String message;
  final bool isUser;
  final List<String>? suggestions;
  final void Function(String)? onSuggestionTap;

  const ChatBubble({
    super.key,
    required this.message,
    required this.isUser,
    this.suggestions,
    this.onSuggestionTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            _buildBotAvatar(),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment:
                  isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: isUser ? AppColors.primary : AppColors.surface,
                    borderRadius:
                        isUser ? WobblyBorders.chatUser : WobblyBorders.chatAi,
                    border: Border.all(
                      color: isUser ? AppColors.primary : AppColors.border,
                    ),
                    boxShadow: const [AppShadows.card],
                  ),
                  child: Text(
                    message,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 16,
                      color: isUser ? AppColors.onPrimary : AppColors.onBackground,
                    ),
                  ),
                ),
                if (!isUser && suggestions != null && suggestions!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: suggestions!
                        .take(3)
                        .map((s) => _buildSuggestionChip(s))
                        .toList(),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBotAvatar() {
    return Container(
      width: 36,
      height: 36,
      decoration: BoxDecoration(
        color: AppColors.surface,
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.border, width: 2),
      ),
      child: const Icon(
        LucideIcons.bot,
        size: 20,
        color: AppColors.secondary,
      ),
    );
  }

  Widget _buildSuggestionChip(String text) {
    return GestureDetector(
      onTap: () => onSuggestionTap?.call(text),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: WobblyBorders.pill,
          border: Border.all(color: AppColors.secondary, width: 1.5),
        ),
        child: Text(
          text,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 13,
            color: AppColors.secondary,
          ),
        ),
      ),
    );
  }
}

/// Typing indicator — three animated dots in a wobbly bubble.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with TickerProviderStateMixin {
  late final List<AnimationController> _controllers;
  late final List<Animation<double>> _animations;

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(3, (i) {
      return AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 600),
      )..repeat(reverse: true);
    });

    _animations = _controllers.asMap().entries.map((e) {
      return Tween<double>(begin: 0, end: -6).animate(
        CurvedAnimation(
          parent: e.value,
          curve: Interval(e.key * 0.2, 0.6 + e.key * 0.2, curve: Curves.easeInOut),
        ),
      );
    }).toList();

    // Stagger start
    for (int i = 0; i < _controllers.length; i++) {
      Future.delayed(Duration(milliseconds: i * 150), () {
        if (mounted) _controllers[i].repeat(reverse: true);
      });
    }
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: AppColors.surface,
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.border, width: 2),
            ),
            child: const Icon(LucideIcons.bot, size: 20, color: AppColors.secondary),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: WobblyBorders.chatAi,
              border: Border.all(color: AppColors.border),
              boxShadow: const [AppShadows.card],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (i) {
                return AnimatedBuilder(
                  animation: _controllers[i],
                  builder: (context, child) {
                    return Transform.translate(
                      offset: Offset(0, _animations[i].value),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: AppColors.onBackground.withValues(alpha: 0.5),
                          shape: BoxShape.circle,
                        ),
                      ),
                    );
                  },
                );
              }),
            ),
          ),
        ],
      ),
    );
  }
}
