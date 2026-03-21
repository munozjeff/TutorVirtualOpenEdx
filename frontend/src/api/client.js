import axios from 'axios'

const api = axios.create({
    baseURL: '',
    withCredentials: true,  // Required for session cookie
    headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
    (res) => res,
    (err) => {
        if (err.response?.status === 401) {
            // Session expired — show helpful message
            console.warn('Session expired. Please re-launch from Open edX.')
        }
        return Promise.reject(err)
    }
)

export const chatApi = {
    sendMessage: (message) =>
        api.post('/api/chat', { message }).then((r) => r.data),

    getHistory: () =>
        api.get('/api/chat/history').then((r) => r.data),

    clearHistory: () =>
        api.delete('/api/chat/history').then((r) => r.data),
}

export const configApi = {
    getMe: () =>
        api.get('/api/config/me').then((r) => r.data),

    getConfig: () =>
        api.get('/api/config').then((r) => r.data),

    updateConfig: (data) =>
        api.put('/api/config', data).then((r) => r.data),

    updateSharing: (data) =>
        api.post('/api/config/sharing', data).then((r) => r.data),
}

// Create a separate axios instance without JSON content-type for file uploads
const uploadApi = axios.create({ baseURL: '', withCredentials: true })

export const documentsApi = {
    list: () =>
        api.get('/api/documents').then((r) => r.data),

    upload: (file, onProgress) => {
        const form = new FormData()
        form.append('file', file)
        return uploadApi.post('/api/documents/upload', form, {
            onUploadProgress: onProgress,
        }).then((r) => r.data)
    },

    delete: (id) =>
        api.delete(`/api/documents/${id}`).then((r) => r.data),
}

export const challengesApi = {
    list: () =>
        api.get('/api/challenges').then((r) => r.data),

    getStatus: () =>
        api.get('/api/challenges/status').then((r) => r.data),

    create: (data) =>
        api.post('/api/challenges', data).then((r) => r.data),

    generate: (data) =>
        api.post('/api/challenges/generate', data).then((r) => r.data),

    update: (id, data) =>
        api.put(`/api/challenges/${id}`, data).then((r) => r.data),

    delete: (id) =>
        api.delete(`/api/challenges/${id}`).then((r) => r.data),
}

export default api
