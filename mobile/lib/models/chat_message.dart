/// Chat message model for AI Health Chat.
class ChatMessage {
  final String role; // 'user' or 'assistant'
  final String content;
  final DateTime timestamp;
  final List<String>? suggestions;

  const ChatMessage({
    required this.role,
    required this.content,
    required this.timestamp,
    this.suggestions,
  });

  bool get isUser => role == 'user';

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        role: json['role'] as String,
        content: json['content'] as String,
        timestamp: DateTime.now(),
        suggestions: (json['suggestions'] as List<dynamic>?)
            ?.map((e) => e.toString())
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'role': role,
        'content': content,
      };
}

/// Response from the AI chat endpoint.
class ChatResponse {
  final String reply;
  final List<String> suggestions;

  const ChatResponse({
    required this.reply,
    this.suggestions = const [],
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
        reply: json['reply'] as String,
        suggestions: (json['suggestions'] as List<dynamic>?)
                ?.map((e) => e.toString())
                .toList() ??
            [],
      );
}
