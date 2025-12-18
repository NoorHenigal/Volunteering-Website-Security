function messageSocket() {
    return {
        ws: null,
        conversationId: null,
        actingAs: 'user',
        actingId: null,
        userId: null,
        newMessage: '',
        typingUser: null,
        connectionStatus: 'disconnected',
        sending: false,
        showScrollButton: false,
        reconnectAttempts: 0,
        maxReconnectAttempts: 5,
        reconnectTimeout: null,
        typingTimeout: null,
        isTyping: false,
        init(conversationId, actingAs, actingId, userId, token) {
            this.conversationId = conversationId;
            this.actingAs = actingAs;
            this.actingId = actingId;
            this.userId = userId;
            this.token = token;
            this.$nextTick(() => this.scrollToBottom());
            this.connect();
        },
        connect() {
            if (!this.token) {
                console.error('No access token provided');
                this.connectionStatus = 'disconnected';
                return;
            }
            this.connectionStatus = 'connecting';
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const params = new URLSearchParams();
            params.set('token', this.token);
            params.set('acting_as', this.actingAs);
            params.set('acting_id', this.actingId || '');
            const wsUrl = `${protocol}//${window.location.host}/ws/messages/${this.conversationId}?${params.toString()}`;
            console.log('Connecting to WebSocket:', wsUrl.substring(0, 100) + '...');
            try {
                this.ws = new WebSocket(wsUrl);
                this.ws.onopen = () => {
                    console.log('WebSocket connected');
                    this.connectionStatus = 'connected';
                    this.reconnectAttempts = 0;
                };
                this.ws.onmessage = (event) => {
                    this.handleMessage(JSON.parse(event.data));
                };
                this.ws.onclose = (event) => {
                    console.log('WebSocket closed:', event.code, event.reason);
                    this.connectionStatus = 'disconnected';
                    this.scheduleReconnect();
                };
                this.ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                };
            } catch (error) {
                console.error('Failed to create WebSocket:', error);
                this.connectionStatus = 'disconnected';
                this.scheduleReconnect();
            }
        },
        scheduleReconnect() {
            if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                console.log('Max reconnect attempts reached');
                return;
            }
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            this.reconnectAttempts++;
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            this.reconnectTimeout = setTimeout(() => {
                this.connect();
            }, delay);
        },
        handleMessage(data) {
            switch (data.type) {
                case 'new_message':
                    this.handleNewMessage(data.message);
                    break;
                case 'typing':
                    this.handleTypingIndicator(data);
                    break;
                case 'read_receipt':
                    this.handleReadReceipt(data);
                    break;
                default:
                    console.log('Unknown message type:', data.type);
            }
        },
        handleNewMessage(message) {
            const isOwn = this.actingAs === 'user'
                ? (message.sender_type === 'user' && message.sender_id === this.userId)
                : (message.sender_type === 'organization' && message.sender_id === this.actingId);
            const messageHtml = this.createMessageBubble(message, isOwn);
            const container = document.getElementById('message-container');
            if (container) {
                container.insertAdjacentHTML('beforeend', messageHtml);
                // Scroll to bottom if near bottom
                const messageList = this.$refs.messageList;
                if (messageList) {
                    const isNearBottom = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < 100;
                    if (isNearBottom || isOwn) {
                        this.$nextTick(() => this.scrollToBottom());
                    }
                }
            }
            if (this.typingUser === message.sender_name) {
                this.typingUser = null;
            }
        },
        createMessageBubble(message, isOwn) {
            const time = new Date(message.created_at).toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
            const bubbleClasses = isOwn
                ? 'bg-gradient-to-br from-brand-500 to-brand-600 text-white shadow-lg shadow-brand-500/20'
                : 'bg-white border border-slate-100 text-slate-800 shadow-sm';
            const cornerClass = isOwn ? 'rounded-br-md' : 'rounded-bl-md';
            const timeClass = isOwn ? 'text-brand-200' : 'text-slate-400';
            const justifyClass = isOwn ? 'justify-end' : '';
            const checkmark = isOwn ? `
<svg class="w-4 h-4 text-brand-200"
     fill="none"
     viewBox="0 0 24 24"
     stroke="currentColor"
     stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
</svg>
` : '';
            return `
<div class="flex ${justifyClass} message-enter">
    <div class="max-w-[75%] ${bubbleClasses} px-4 py-2.5 rounded-2xl ${cornerClass}">
        <p class="text-sm leading-relaxed whitespace-pre-wrap break-words">${this.escapeHtml(message.content)}</p>
        <div class="flex items-center ${isOwn ? 'justify-end' : ''} gap-1.5 mt-1">
            <span class="text-xs ${timeClass} tabular-nums">${time}</span>
            ${checkmark}
        </div>
    </div>
</div>
`;
        },
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },
        handleTypingIndicator(data) {
            if (data.is_typing) {
                this.typingUser = data.sender_name;
                setTimeout(() => { if (this.typingUser === data.sender_name) this.typingUser = null; }, 3000);
            } else if (this.typingUser === data.sender_name) {
                this.typingUser = null;
            }
        },
        handleReadReceipt(data) {
            console.log('Read receipt:', data);
        },
        sendMessage() {
            if (!this.newMessage.trim() || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
                return;
            }
            this.sending = true;
            try {
                this.ws.send(JSON.stringify({
                    type: 'message',
                    content: this.newMessage.trim()
                }));
                this.newMessage = '';
                this.stopTyping();
                // Reset textarea height
                if (this.$refs.messageInput) {
                    this.$refs.messageInput.style.height = 'auto';
                }
            } catch (error) {
                console.error('Failed to send message:', error);
            } finally {
                this.sending = false;
            }
        },
        handleTyping() {
            if (!this.isTyping && this.newMessage.trim()) {
                this.isTyping = true;
                this.sendTypingIndicator(true);
            }
            if (this.typingTimeout) clearTimeout(this.typingTimeout);
            this.typingTimeout = setTimeout(() => {
                this.stopTyping();
            }, 2000);
        },
        stopTyping() {
            if (this.isTyping) { this.isTyping = false; this.sendTypingIndicator(false); }
            if (this.typingTimeout) { clearTimeout(this.typingTimeout); this.typingTimeout = null; }
        },
        sendTypingIndicator(isTyping) {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({
                    type: 'typing',
                    is_typing: isTyping
                }));
            }
        },
        scrollToBottom() {
            this.$refs.messageList?.scrollTo({ top: this.$refs.messageList.scrollHeight, behavior: 'smooth' });
        },
        onScroll() {
            const el = this.$refs.messageList;
            if (el) this.showScrollButton = el.scrollHeight - el.scrollTop - el.clientHeight > 200;
        },
        disconnect() {
            if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
            if (this.typingTimeout) clearTimeout(this.typingTimeout);
            if (this.ws) { this.ws.close(); this.ws = null; }
        }
    };
}
function inboxSocket() {
    return {
        ws: null,
        actingAs: 'user',
        actingId: null,
        token: null,
        init(actingAs, actingId, token) {
            this.actingAs = actingAs;
            this.actingId = actingId;
            this.token = token;
            this.connect();
        },
        connect() {
            if (!this.token) {
                console.log('Inbox WebSocket: No token, skipping connection');
                return;
            }
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const params = new URLSearchParams({
                token: this.token,
                acting_as: this.actingAs,
                acting_id: this.actingId || ''
            });
            const wsUrl = `${protocol}//${window.location.host}/ws/inbox?${params}`;
            console.log('Inbox WebSocket connecting as:', this.actingAs, this.actingId);
            try {
                this.ws = new WebSocket(wsUrl);
                this.ws.onopen = () => {
                    console.log('Inbox WebSocket connected');
                };
                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log('Inbox WebSocket received:', data);
                    if (data.type === 'inbox_update') {
                        this.handleInboxUpdate(data);
                    }
                };
                this.ws.onclose = (event) => {
                    console.log('Inbox WebSocket closed:', event.code, event.reason);
                    setTimeout(() => this.connect(), 3000);
                };
                this.ws.onerror = (error) => {
                    console.error('Inbox WebSocket error:', error);
                };
            } catch (error) {
                console.error('Inbox WebSocket connection error:', error);
            }
        },
        handleInboxUpdate(data) {
            const link = document.querySelector(`a[data-conversation-id="${data.conversation_id}"]`);
            if (!link) { window.location.reload(); return; }
            const previewEl = link.querySelector('p.truncate');
            if (previewEl) previewEl.textContent = data.message_preview;
            if (this.selectedId !== data.conversation_id) {
                previewEl?.classList.add('font-medium', 'text-slate-700');
                if (!link.querySelector('.unread-dot')) {
                    const container = link.querySelector('.flex.items-center.gap-2');
                    if (container) {
                        const dot = document.createElement('span');
                        dot.className = 'unread-dot flex-shrink-0 w-2.5 h-2.5 bg-brand-500 rounded-full animate-pulse';
                        container.appendChild(dot);
                    }
                }
            }
            const parent = link.parentElement;
            if (parent?.firstChild !== link) parent.insertBefore(link, parent.firstChild);
            link.classList.add('bg-brand-50');
            setTimeout(() => link.classList.remove('bg-brand-50'), 2000);
        },
        disconnect() {
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
        }
    };
}
window.messageSocket = messageSocket;
window.inboxSocket = inboxSocket;
