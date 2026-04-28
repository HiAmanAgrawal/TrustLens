import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/chat_message.dart';
import '../models/scan_result.dart';
import 'service_providers.dart';

/// Chat state for the AI Health Chat.
class ChatState {
  final List<ChatMessage> messages;
  final bool isTyping;
  final ScanResult? scanContext;

  const ChatState({
    this.messages = const [],
    this.isTyping = false,
    this.scanContext,
  });

  ChatState copyWith({
    List<ChatMessage>? messages,
    bool? isTyping,
    ScanResult? scanContext,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      isTyping: isTyping ?? this.isTyping,
      scanContext: scanContext ?? this.scanContext,
    );
  }
}

class ChatNotifier extends StateNotifier<ChatState> {
  final Ref ref;

  ChatNotifier(this.ref) : super(const ChatState());

  /// Initialize chat with optional scan context.
  void initWithContext(ScanResult? scanResult) {
    final messages = <ChatMessage>[];
    if (scanResult != null) {
      messages.add(ChatMessage(
        role: 'assistant',
        content: 'I analyzed your scan. Here\'s what I found \u2014 '
            'feel free to ask me anything about it.\n\n'
            'Product: ${scanResult.productName}\n'
            'Verdict: ${scanResult.verdict} (${scanResult.score}/10)\n'
            'Summary: ${scanResult.summary}',
        timestamp: DateTime.now(),
        suggestions: ['What about side effects?', 'Is it safe for me?', 'Any interactions?'],
      ));
    } else {
      messages.add(ChatMessage(
        role: 'assistant',
        content: 'Hi! I\'m your AI Health Assistant. Ask me anything about '
            'medicines, food safety, ingredients, or your health.\n\n'
            '\u26A0 Remember: I provide information, not medical advice.',
        timestamp: DateTime.now(),
        suggestions: ['How to read a food label?', 'What is FSSAI?', 'Common allergens?'],
      ));
    }

    state = ChatState(
      messages: messages,
      scanContext: scanResult,
    );
  }

  /// Send a user message and get AI response.
  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final userMsg = ChatMessage(
      role: 'user',
      content: text.trim(),
      timestamp: DateTime.now(),
    );

    state = state.copyWith(
      messages: [...state.messages, userMsg],
      isTyping: true,
    );

    try {
      final api = ref.read(mockApiServiceProvider);
      final response = await api.sendChatMessage(
        messages: state.messages,
      );

      final aiMsg = ChatMessage(
        role: 'assistant',
        content: response.reply,
        timestamp: DateTime.now(),
        suggestions: response.suggestions,
      );

      state = state.copyWith(
        messages: [...state.messages, aiMsg],
        isTyping: false,
      );
    } catch (e) {
      final errorMsg = ChatMessage(
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: DateTime.now(),
      );

      state = state.copyWith(
        messages: [...state.messages, errorMsg],
        isTyping: false,
      );
    }
  }

  /// Clear chat history.
  void clearChat() {
    state = const ChatState();
  }
}

final chatProvider = StateNotifierProvider<ChatNotifier, ChatState>((ref) {
  return ChatNotifier(ref);
});
