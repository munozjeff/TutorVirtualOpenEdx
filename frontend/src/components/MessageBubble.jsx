import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function formatTime(isoString) {
    const d = new Date(isoString)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function MessageBubble({ message }) {
    const isUser = message.role === 'user'

    return (
        <div className={`message message--${isUser ? 'user' : 'ai'}`}>
            <div className={`message__avatar message__avatar--${isUser ? 'user' : 'ai'}`}>
                {isUser ? '👤' : '🤖'}
            </div>

            <div className="message__body">
                <div className={`message__bubble message__bubble--${isUser ? 'user' : 'ai'}`}>
                    {isUser ? (
                        message.content
                    ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {message.content}
                        </ReactMarkdown>
                    )}
                </div>
                {message.created_at && (
                    <span className="message__time">{formatTime(message.created_at)}</span>
                )}
            </div>
        </div>
    )
}
