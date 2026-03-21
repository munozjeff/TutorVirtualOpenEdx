import { useState, useEffect, useRef, useCallback } from 'react'
import { chatApi, configApi } from '../api/client'

export function useChat() {
    const [messages, setMessages] = useState([])
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [userInfo, setUserInfo] = useState(null)
    const [config, setConfig] = useState(null)
    const [isInitialized, setIsInitialized] = useState(false)

    // Load user info + history on mount
    useEffect(() => {
        const init = async () => {
            try {
                const [me, history, cfg] = await Promise.all([
                    configApi.getMe(),
                    chatApi.getHistory(),
                    configApi.getConfig(),
                ])
                setUserInfo(me)
                setConfig(cfg)
                setMessages(history)

                // Add welcome message if no history
                if (history.length === 0 && cfg.welcome_message) {
                    setMessages([
                        { role: 'assistant', content: cfg.welcome_message, created_at: new Date().toISOString() },
                    ])
                }
            } catch (err) {
                setError(err.response?.data?.detail || 'No se pudo iniciar la sesión. Lanza el tutor desde Open edX.')
            } finally {
                setIsInitialized(true)
            }
        }
        init()
    }, [])

    const sendMessage = useCallback(async (text) => {
        if (!text.trim() || isLoading) return

        const userMsg = { role: 'user', content: text, created_at: new Date().toISOString() }
        setMessages((prev) => [...prev, userMsg])
        setIsLoading(true)
        setError(null)

        try {
            const data = await chatApi.sendMessage(text)
            const assistantMsg = { role: 'assistant', content: data.reply, created_at: new Date().toISOString() }
            setMessages((prev) => [...prev, assistantMsg])
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al enviar el mensaje. Intenta de nuevo.')
            // Remove optimistic user message on error
            setMessages((prev) => prev.slice(0, -1))
        } finally {
            setIsLoading(false)
        }
    }, [isLoading])

    const clearHistory = useCallback(async () => {
        try {
            await chatApi.clearHistory()
            setMessages(
                config?.welcome_message
                    ? [{ role: 'assistant', content: config.welcome_message, created_at: new Date().toISOString() }]
                    : []
            )
        } catch (err) {
            setError('No se pudo borrar el historial.')
        }
    }, [config])

    return {
        messages,
        isLoading,
        error,
        userInfo,
        config,
        isInitialized,
        sendMessage,
        clearHistory,
        setConfig,
    }
}
