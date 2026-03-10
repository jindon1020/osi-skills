const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { execSync, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');

const app = express();
const PORT = process.env.PORT || 3003;

// 中间件
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

// 文件上传配置
const upload = multer({
  dest: 'uploads/',
  limits: { fileSize: 50 * 1024 * 1024 }
});

// 确保上传目录存在
if (!fs.existsSync('uploads')) {
  fs.mkdirSync('uploads');
}

// 会话存储
const sessions = new Map();

// 首页
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 流式对话 API
app.post('/api/chat', upload.array('files'), async (req, res) => {
  const { message, sessionId } = req.body;
  const files = req.files || [];

  // 设置 SSE 头
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'none');

  try {
    // 获取或创建会话
    let session = sessions.get(sessionId);
    if (!session) {
      session = { id: sessionId, history: [] };
      sessions.set(sessionId, session);
    }

    // 添加用户消息到历史
    session.history.push({ role: 'user', content: message });

    // 构建消息内容
    let fullMessage = message;

    // 如果有附件，添加到上下文中
    if (files && files.length > 0) {
      const fileDescriptions = files.map(f => `[上传文件: ${f.originalname}]`).join(' ');
      fullMessage = `${fileDescriptions}\n\n${message}`;
    }

    // 添加历史上下文
    if (session.history.length > 1) {
      const recentHistory = session.history.slice(-10, -1);
      const context = recentHistory.map(h => `${h.role === 'user' ? '用户' : '助手'}: ${h.content}`).join('\n\n');
      fullMessage = `对话历史:\n${context}\n\n---\n\n当前问题: ${fullMessage}`;
    }

    // 发送开始信号
    res.write(`data: ${JSON.stringify({ type: 'start' })}\n\n`);

    // 构建环境变量
    const env = {
      ...process.env,
      ANTHROPIC_AUTH_TOKEN: 'sk-cp-MWmY5LHRY9viQ_ShLvpRaIm5EU56NntUFM5f-HigNQ2-WSqAz0krDgEhUzhMIf2XCjQwyUWfFHchNfGRi0JoHqnTtjQ2yt9XHYTsUhYy9fCkDrZb-_DhgPo',
      ANTHROPIC_BASE_URL: 'https://api.minimaxi.com/anthropic',
      ANTHROPIC_MODEL: 'MiniMax-M2.5',
      API_TIMEOUT_MS: '300000'
    };

    // 使用 execSync 同步执行
    const escapedMessage = fullMessage.replace(/'/g, "'\\''");
    const command = `claude --print -p '${escapedMessage}'`;

    console.log('Executing:', command);

    let output = '';
    try {
      output = execSync(command, {
        env: env,
        encoding: 'utf8',
        timeout: 120000,
        maxBuffer: 10 * 1024 * 1024
      });
    } catch (execError) {
      console.error('Exec error:', execError.message);
      output = execError.stdout || execError.message;
    }

    // 发送内容
    res.write(`data: ${JSON.stringify({ type: 'content', content: output })}\n\n`);

    // 添加到历史
    if (output) {
      session.history.push({ role: 'assistant', content: output });
      if (session.history.length > 20) {
        session.history = session.history.slice(-20);
      }
    }

    // 发送结束
    res.write(`data: ${JSON.stringify({ type: 'end', content: output })}\n\n`);
    res.end();

    // 清理上传的文件
    files.forEach(f => {
      try {
        fs.unlinkSync(f.path);
      } catch (e) {}
    });

  } catch (error) {
    console.error('Error:', error);
    res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
    res.end();
  }
});

// 确认执行 API
app.post('/api/confirm', (req, res) => {
  const { sessionId, confirmed } = req.body;
  const session = sessions.get(sessionId);
  if (session) {
    session.confirmed = confirmed;
    session.waitingForConfirm = false;
  }
  res.json({ success: true });
});

// 获取会话历史
app.get('/api/sessions/:sessionId', (req, res) => {
  const { sessionId } = req.params;
  const session = sessions.get(sessionId);
  if (session) {
    res.json({ history: session.history });
  } else {
    res.json({ history: [] });
  }
});

// 创建新会话
app.post('/api/sessions', (req, res) => {
  const sessionId = uuidv4();
  sessions.set(sessionId, { id: sessionId, history: [] });
  res.json({ sessionId });
});

// 删除会话
app.delete('/api/sessions/:sessionId', (req, res) => {
  const { sessionId } = req.params;
  sessions.delete(sessionId);
  res.json({ success: true });
});

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Web Claude Code 服务已启动: http://0.0.0.0:${PORT}`);
});
