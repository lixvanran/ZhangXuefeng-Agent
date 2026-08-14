/** API 统一出口
v0.7.5 模块化: 按 endpoint 拆到独立文件, 这里只 re-export
- chat.ts: streamChat
- user.ts: getUserProfile / updateUserProfile / getEducationStages
- conversations.ts: 5 个会话接口
- resources.ts: 8 个资料接口
- tts.ts: tts / getVoices
- toggles.ts: getToggle / setToggle
- client.ts: axios 实例
*/
export { default as api } from './client'
export * from './chat'
export * from './user'
export * from './conversations'
export * from './resources'
export * from './tts'
export * from './toggles'
export * from './workspace'
