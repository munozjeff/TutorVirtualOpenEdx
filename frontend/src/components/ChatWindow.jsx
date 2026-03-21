import { useEffect, useRef, useState, useCallback } from 'react'
import MessageBubble from './MessageBubble'

export default function ChatWindow({ messages, isLoading, onSend, error }) {
    const [input, setInput] = useState('')
    const messagesEndRef = useRef(null)
    const textareaRef = useRef(null)

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, isLoading])

    const handleSend = useCallback(() => {
        if (!input.trim() || isLoading) return
        onSend(input.trim())
        setInput('')
        textareaRef.current?.focus()
    }, [input, isLoading, onSend])

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    const handleInput = (e) => {
        setInput(e.target.value)
        // Auto-resize textarea
        e.target.style.height = 'auto'
        e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
    }

    return (
        <div className="chat-container">
            {/* Messages */}
            <div className="messages-area">
                <div className="messages-list">
                    {messages.map((msg, i) => (
                        <MessageBubble key={i} message={msg} />
                    ))}

                    {isLoading && (
                        <div className="message message--ai">
                            <div className="message__avatar message__avatar--ai">🤖</div>
                            <div className="message__body">
                                <div className="message__bubble message__bubble--ai">
                                    <div className="typing-indicator">
                                        <div className="typing-dot" />
                                        <div className="typing-dot" />
                                        <div className="typing-dot" />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="error-banner">
                    <span>⚠️</span> {error}
                </div>
            )}

            {/* Input */}
            <div className="input-area">
                <div className="input-wrapper">
                    <textarea
                        ref={textareaRef}
                        className="chat-input"
                        placeholder="Escribe tu pregunta… (Enter para enviar, Shift+Enter para nueva línea)"
                        value={input}
                        onChange={handleInput}
                        onKeyDown={handleKeyDown}
                        rows={1}
                        disabled={isLoading}
                    />
                    <button
                        className="send-btn"
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading}
                        title="Enviar mensaje"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13" />
                            <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    )
}
