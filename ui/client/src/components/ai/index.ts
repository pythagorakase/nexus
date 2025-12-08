/**
 * AI Components - Chat UI components for NEXUS
 *
 * Based on shadcn/ui (https://ui.shadcn.com/)
 * Copyright (c) 2024 shadcn
 * Licensed under the Apache License, Version 2.0
 * See: ui/licenses/SHADCN-AI-LICENSE
 *
 * Components:
 * - Conversation: Auto-scrolling container with StickToBottom
 * - Message: User/assistant chat message bubbles
 * - PromptInput: Chat input with model picker integration
 * - Response: Streaming-aware markdown renderer
 * - Loader: Spinning loader icon
 */

export {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  type ConversationProps,
  type ConversationContentProps,
  type ConversationScrollButtonProps,
} from './conversation';

export {
  Message,
  MessageContent,
  MessageAvatar,
  type MessageRole,
  type MessageProps,
  type MessageContentProps,
  type MessageAvatarProps,
} from './message';

export {
  PromptInput,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
  PromptInputButton,
  PromptInputSubmit,
  PromptInputModelSelect,
  PromptInputModelSelectTrigger,
  PromptInputModelSelectContent,
  PromptInputModelSelectItem,
  PromptInputModelSelectValue,
  type ChatStatus,
  type PromptInputProps,
  type PromptInputTextareaProps,
  type PromptInputToolbarProps,
  type PromptInputToolsProps,
  type PromptInputButtonProps,
  type PromptInputSubmitProps,
  type PromptInputModelSelectProps,
  type PromptInputModelSelectTriggerProps,
  type PromptInputModelSelectContentProps,
  type PromptInputModelSelectItemProps,
  type PromptInputModelSelectValueProps,
} from './prompt-input';

export { Response, type ResponseProps } from './response';

export { Loader, type LoaderProps } from './loader';
