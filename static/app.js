```javascript
/**
 * AI Video Generator - Frontend Application
 * Handles chat interactions, sidebar toggle, message animations, and video display
 */

// Wait for DOM to be fully loaded before initializing
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

/**
 * Main application initialization
 */
function initApp() {
    // Cache DOM elements
    const elements = {
        chatForm: document.getElementById('chat-form'),
        userInput: document.getElementById('user-input'),
        chatMessages: document.getElementById('chat-messages'),
        sidebar: document.getElementById('sidebar'),
        sidebarToggle: document.getElementById('sidebar-toggle'),
        sidebarOverlay: document.getElementById('sidebar-overlay'),
        videoModal: document.getElementById('video-modal'),
        videoPlayer: document.getElementById('video-player'),
        closeVideo: document.getElementById('close-video'),
        loadingIndicator: document.getElementById('loading-indicator'),
        sendButton: document.getElementById('send-button'),
        clearChat: document.getElementById('clear-chat'),
        historyList: document.getElementById('history-list')
    };

    // Validate required elements exist
    if (!elements.chatForm || !elements.userInput || !elements.chatMessages) {
        console.error('Required DOM elements not found');
        return;
    }

    // Application state
    const state = {
        isLoading: false,
        currentVideoUrl: null,
        messageQueue: [],
        isAnimating: false
    };

    // Initialize event listeners
    initEventListeners(elements, state);
    
    // Load chat history
    loadChatHistory(elements);
    
    // Auto-resize textarea
    initTextareaAutoResize(elements.userInput);
}

/**
 * Initialize all event listeners
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 */
function initEventListeners(elements, state) {
    // Chat form submission
    elements.chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        handleChatSubmit(elements, state);
    });

    // Sidebar toggle
    if (elements.sidebarToggle) {
        elements.sidebarToggle.addEventListener('click', () => {
            toggleSidebar(elements);
        });
    }

    // Sidebar overlay click to close
    if (elements.sidebarOverlay) {
        elements.sidebarOverlay.addEventListener('click', () => {
            closeSidebar(elements);
        });
    }

    // Close video modal
    if (elements.closeVideo) {
        elements.closeVideo.addEventListener('click', () => {
            closeVideoModal(elements, state);
        });
    }

    // Click outside video modal to close
    if (elements.videoModal) {
        elements.videoModal.addEventListener('click', (e) => {
            if (e.target === elements.videoModal) {
                closeVideoModal(elements, state);
            }
        });
    }

    // Clear chat button
    if (elements.clearChat) {
        elements.clearChat.addEventListener('click', () => {
            clearChat(elements, state);
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape to close sidebar or video modal
        if (e.key === 'Escape') {
            if (elements.sidebar && elements.sidebar.classList.contains('open')) {
                closeSidebar(elements);
            }
            if (elements.videoModal && elements.videoModal.classList.contains('open')) {
                closeVideoModal(elements, state);
            }
        }
        
        // Ctrl+Enter to submit
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleChatSubmit(elements, state);
        }
    });

    // Handle input keydown for Enter to submit (without shift)
    elements.userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleChatSubmit(elements, state);
        }
    });
}

/**
 * Handle chat form submission
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 */
async function handleChatSubmit(elements, state) {
    const message = elements.userInput.value.trim();
    
    if (!message || state.isLoading) return;

    // Clear input and set loading state
    elements.userInput.value = '';
    setLoadingState(elements, state, true);

    // Add user message to chat
    addMessageToChat('user', message, elements, state);
    
    // Reset textarea height
    resetTextareaHeight(elements.userInput);

    try {
        // Send message to backend
        const response = await sendMessageToBackend(message);
        
        // Add bot response to chat
        if (response && response.message) {
            addMessageToChat('bot', response.message, elements, state, response.video_url);
        } else {
            addMessageToChat('bot', 'I received your request but encountered an issue processing it.', elements, state);
        }
    } catch (error) {
        console.error('Error sending message:', error);
        addMessageToChat('bot', 'Sorry, I encountered an error processing your request. Please try again.', elements, state);
    } finally {
        setLoadingState(elements, state, false);
    }
}

/**
 * Send message to backend API
 * @param {string} message - User message
 * @returns {Promise<Object>} - Response data
 */
async function sendMessageToBackend(message) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message })
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
}

/**
 * Add a message to the chat interface
 * @param {string} type - 'user' or 'bot'
 * @param {string} content - Message content
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 * @param {string} [videoUrl] - Optional video URL for bot messages
 */
function addMessageToChat(type, content, elements, state, videoUrl = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    messageDiv.style.opacity = '0';
    messageDiv.style.transform = 'translateY(20px)';

    // Create message content
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Parse markdown-like formatting
    contentDiv.innerHTML = formatMessageContent(content);

    // Add video player if video URL is provided
    if (videoUrl && type === 'bot') {
        const videoContainer = createVideoContainer(videoUrl, elements, state);
        contentDiv.appendChild(videoContainer);
    }

    messageDiv.appendChild(contentDiv);

    // Add timestamp
    const timestamp = document.createElement('div');
    timestamp.className = 'message-timestamp';
    timestamp.textContent = new Date().toLocaleTimeString();
    messageDiv.appendChild(timestamp);

    // Add to chat
    elements.chatMessages.appendChild(messageDiv);

    // Animate message appearance
    requestAnimationFrame(() => {
        messageDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        messageDiv.style.opacity = '1';
        messageDiv.style.transform = 'translateY(0)';
    });

    // Scroll to bottom
    scrollToBottom(elements.chatMessages);

    // Save to history
    saveMessageToHistory(type, content, videoUrl);
}

/**
 * Format message content with basic markdown-like formatting
 * @param {string} content - Raw message content
 * @returns {string} - Formatted HTML content
 */
function formatMessageContent(content) {
    if (!content) return '';

    // Escape HTML to prevent XSS
    let formatted = escapeHtml(content);

    // Convert URLs to links
    formatted = formatted.replace(
        /(https?:\/\/[^\s<]+)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    // Convert newlines to <br>
    formatted = formatted.replace(/\n/g, '<br>');

    // Convert bold text
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Convert italic text
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');

    return formatted;
}

/**
 * Escape HTML to prevent XSS attacks
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Create video container element
 * @param {string} videoUrl - URL of the video
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 * @returns {HTMLElement} - Video container element
 */
function createVideoContainer(videoUrl, elements, state) {
    const container = document.createElement('div');
    container.className = 'video-container';

    const video = document.createElement('video');
    video.className = 'chat-video';
    video.src = videoUrl;
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;

    // Add click to expand functionality
    video.addEventListener('click', () => {
        openVideoModal(videoUrl, elements, state);
    });

    // Add loading state
    video.addEventListener('loadstart', () => {
        container.classList.add('loading');
    });

    video.addEventListener('canplay', () => {
        container.classList.remove('loading');
    });

    // Error handling
    video.addEventListener('error', () => {
        container.classList.add('error');
        const errorMsg = document.createElement('p');
        errorMsg.className = 'video-error';
        errorMsg.textContent = 'Failed to load video';
        container.appendChild(errorMsg);
    });

    container.appendChild(video);

    // Add expand button
    const expandBtn = document.createElement('button');
    expandBtn.className = 'video-expand-btn';
    expandBtn.innerHTML = '⛶';
    expandBtn.title = 'Expand video';
    expandBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openVideoModal(videoUrl, elements, state);
    });
    container.appendChild(expandBtn);

    return container;
}

/**
 * Open video modal with full-size player
 * @param {string} videoUrl - URL of the video
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 */
function openVideoModal(videoUrl, elements, state) {
    if (!elements.videoModal || !elements.videoPlayer) return;

    state.currentVideoUrl = videoUrl;
    elements.videoPlayer.src = videoUrl;
    elements.videoModal.classList.add('open');
    document.body.style.overflow = 'hidden';

    // Auto-play when modal opens
    elements.videoPlayer.play().catch(error => {
        console.warn('Auto-play was prevented:', error);
    });
}

/**
 * Close video modal
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 */
function closeVideoModal(elements, state) {
    if (!elements.videoModal || !elements.videoPlayer) return;

    elements.videoPlayer.pause();
    elements.videoPlayer.src = '';
    elements.videoModal.classList.remove('open');
    document.body.style.overflow = '';
    state.currentVideoUrl = null;
}

/**
 * Toggle sidebar open/close
 * @param {Object} elements - Cached DOM elements
 */
function toggleSidebar(elements) {
    if (!elements.sidebar) return;

    const isOpen = elements.sidebar.classList.toggle('open');
    
    if (elements.sidebarOverlay) {
        elements.sidebarOverlay.classList.toggle('open', isOpen);
    }

    // Update aria attributes
    elements.sidebar.setAttribute('aria-hidden', !isOpen);
    
    if (elements.sidebarToggle) {
        elements.sidebarToggle.setAttribute('aria-expanded', isOpen);
    }

    // Prevent body scroll when sidebar is open on mobile
    if (window.innerWidth <= 768) {
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }
}

/**
 * Close sidebar
 * @param {Object} elements - Cached DOM elements
 */
function closeSidebar(elements) {
    if (!elements.sidebar) return;

    elements.sidebar.classList.remove('open');
    
    if (elements.sidebarOverlay) {
        elements.sidebarOverlay.classList.remove('open');
    }

    elements.sidebar.setAttribute('aria-hidden', 'true');
    
    if (elements.sidebarToggle) {
        elements.sidebarToggle.setAttribute('aria-expanded', 'false');
    }

    document.body.style.overflow = '';
}

/**
 * Set loading state for the chat interface
 * @param {Object} elements - Cached DOM elements
 * @param {Object} state - Application state
 * @param {boolean} isLoading - Whether to show loading state
 */
function setLoadingState(elements, state, isLoading) {
    state.isLoading = isLoading;

    if (elements.sendButton) {
        elements.sendButton.disabled = isLoading;
        elements.sendButton.innerHTML = isLoading ? 
            '<span class="spinner"></span> Sending...' : 
            'Send';
    }

    if (elements.userInput) {
        elements.userInput.disabled = isLoading;
    }

    if (elements.loadingIndicator) {
        elements.loadingIndicator.style.display = isLoading ? 'flex' : 'none';
    }
}

/**
 * Scroll chat messages to bottom
 * @param {HTMLElement} container - Chat messages container
 */
function scrollToBottom(container) {
    if (!container) return;
    
    requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
    });
}

/**
 * Initialize textarea auto-resize
 * @param {HTMLTextAreaElement} textarea - Textarea element
 */
function initTextareaAutoResize(textarea) {
    if (!textarea) return;

    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    });
}

/**
 * Reset textarea height to default
 * @param {HTMLTextAreaElement} textarea - Textarea element
 */
function resetTextareaHeight(textarea) {
    if (!textarea) return;
    textarea.style.height = 'auto';
}

/**
 * Save message to chat history
 * @param {string} type - 'user' or 'bot'
 * @param {string} content - Message content
 * @param {string} [videoUrl] - Optional video URL
 */
function saveMessageToHistory(type, content, videoUrl = null) {
    try {
        const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        
        history.push({
            type,
            content,
            videoUrl,
            timestamp: new Date().toISOString()
        });

        // Keep only last 100 messages
        if (history.length > 100) {
            history.splice(0, history.length - 100);
        }

        localStorage.setItem('chatHistory', JSON.stringify(history));
    } catch (error) {
        console.error('Error saving to history:', error);
    }
}

/**
 * Load chat history from localStorage
 * @param {Object} elements - Cached DOM elements
 */
function loadChatHistory(elements) {
    try {
        const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        
        // Clear existing messages except welcome message
        const welcomeMessage = elements.chatMessages.querySelector('.bot-message:first-child');
        elements.chatMessages.innerHTML = '';
        
        if (welcomeMessage) {
            elements.chatMessages.appendChild(welcomeMessage);
        }

        // Add history messages
        history.forEach(msg => {
            addMessageToChat(msg.type, msg.content, elements, { isLoading: false, isAnimating: false }, msg.videoUrl);
        });

        // Update history list in sidebar
        updateHistoryList(elements);
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

/**
 * Update history list in sidebar
 * @param {Object} elements - Cached DOM elements
 */
function updateHistoryList(elements) {
    if (!elements.historyList) return;

    try {
        const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        const userMessages = history.filter(msg => msg.type === 'user');
        
        elements.historyList.innerHTML = '';

        if (userMessages.length === 0) {
            elements.historyList.innerHTML = '<li class="history-empty">No chat history yet</li>';
            return;
        }

        // Show last 10 user messages
        const recentMessages = userMessages.slice(-10);
        
        recentMessages.forEach(msg => {
            const li = document.createElement('li');
            li.className = 'history-item';
            
            const content = document.createElement('span');
            content.className = 'history-content';
            content.textContent = msg.content.substring(0, 50) + (msg.content.length > 50 ? '...' : '');
            
            const timestamp = document.createElement('span');
            timestamp.className = 'history-timestamp';
            timestamp.textContent = new Date(msg.timestamp).toLocaleDateString();
            
            li.appendChild(content);
            li.appendChild(timestamp);
            
            li.addEventListener('click', () => {
                // Load this conversation
                loadConversation(msg.timestamp, elements);
                closeSidebar(elements);
            });
            
            elements.historyList.appendChild(li);
        });
    } catch (error) {
        console.error('Error updating history list:', error);
    }
}

/**
 * Load a specific conversation from history
 * @param {string} timestamp - Timestamp of the conversation to load
 * @param {Object} elements - Cached DOM elements
 */
function loadConversation(timestamp, elements) {
    try {
        const history = JSON.parse(localStorage.getItem('chatHistory') || '[]');
        const conversation = [];
        let found =