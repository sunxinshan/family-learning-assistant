import { actionApi, learningApi, taskApi, vocabularyApi } from './mockApi'
import type {
  AgentEvent,
  LearningTask,
  PendingAction,
  TaskDraft,
  ToolExecution,
  VocabularyDraft,
} from '../types/domain'

type Emit = (event: AgentEvent) => void

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const id = (prefix: string) => `${prefix}-${crypto.randomUUID()}`
const stamp = () => new Date().toISOString()

const emitTool = async <T,>(
  emit: Emit,
  tool: string,
  label: string,
  args: Record<string, unknown>,
  operation: () => Promise<T> | T,
  summarize: (result: T) => string,
): Promise<T> => {
  const execution: ToolExecution = {
    id: id('tool'),
    tool,
    label,
    status: 'running',
    args,
    startedAt: stamp(),
  }
  emit({ type: 'tool_status', data: execution })
  await wait(360)
  const started = performance.now()
  try {
    const result = await operation()
    emit({
      type: 'tool_status',
      data: {
        ...execution,
        status: 'success',
        durationMs: Math.round(performance.now() - started),
        result: summarize(result),
      },
    })
    return result
  } catch (error) {
    emit({
      type: 'tool_status',
      data: {
        ...execution,
        status: 'error',
        durationMs: Math.round(performance.now() - started),
        error: error instanceof Error ? error.message : '未知错误',
      },
    })
    throw error
  }
}

const findQuoted = (text: string): string | undefined =>
  text.match(/[「“"]([^」”"]+)[」”"]/)?.[1]

const extractNumber = (text: string, patterns: RegExp[], fallback: number): number => {
  for (const pattern of patterns) {
    const value = Number(text.match(pattern)?.[1])
    if (Number.isFinite(value) && value > 0) return value
  }
  return fallback
}

const taskTypeFromText = (text: string): 'vocabulary' | 'dictation' | undefined => {
  if (/听写/.test(text)) return 'dictation'
  if (/词汇|单词|背词|词库/.test(text)) return 'vocabulary'
  return undefined
}

const modeFromText = (text: string): 'fixed' | 'long_term' =>
  /固定|一次|单次/.test(text) ? 'fixed' : 'long_term'

const taskDraftFromText = async (
  text: string,
  userId: string,
  taskType: 'vocabulary' | 'dictation',
): Promise<TaskDraft> => {
  const libraries = vocabularyApi.listMine(userId)
  const quoted = findQuoted(text)
  const matchedLibrary =
    libraries.find((library) => quoted && library.name.includes(quoted)) ??
    libraries.find((library) => text.includes(library.name)) ??
    libraries.find((library) =>
      taskType === 'dictation'
        ? library.name.includes('旅行') || library.name.includes('听写')
        : library.name.includes('日常') || library.name.includes('核心'),
    ) ??
    libraries[0]
  if (!matchedLibrary) {
    throw new Error('你还没有个人词库，请先创建或复制一个词库')
  }
  const allWords = /所有|全部/.test(text)
  const targetCount = Math.min(
    allWords
      ? matchedLibrary.entries.length
      : extractNumber(text, [/每天\s*(\d+)\s*个/, /(\d+)\s*(?:个词|道题|个单词|项)/], 10),
    matchedLibrary.entries.length,
  )
  const wordsPerGroup = Math.min(
    extractNumber(text, [/每组\s*(\d+)\s*个/, /每天\s*(\d+)\s*个/], targetCount),
    targetCount,
  )
  const cleanQuotedName = findQuoted(text.replace(/[「“"]\d+[」”"]/g, ''))
  const mode = modeFromText(text)
  return {
    name:
      cleanQuotedName && !matchedLibrary.name.includes(cleanQuotedName)
        ? cleanQuotedName
        : taskType === 'dictation'
          ? `${matchedLibrary.name} · 听写`
          : `每日词汇 · ${matchedLibrary.name}`,
    type: taskType,
    mode,
    targetCount: mode === 'fixed' ? matchedLibrary.entries.length : targetCount,
    libraryId: matchedLibrary.id,
    selectedEntryIds:
      mode === 'fixed' || allWords
        ? matchedLibrary.entries.map((entry) => entry.id)
        : matchedLibrary.entries.slice(0, targetCount).map((entry) => entry.id),
    wordsPerGroup: mode === 'fixed' ? matchedLibrary.entries.length : wordsPerGroup,
    repeatUntilCorrect: /必须答对|答对才能|强制/.test(text),
    ...(taskType === 'dictation'
      ? {
          dictation: {
            mode: /线下听写/.test(text) ? 'offline' as const : 'online' as const,
            playbackMode: /自动播放|自动/.test(text) ? 'auto' as const : 'manual' as const,
            intervalSeconds: extractNumber(
              text,
              [/间隔\s*(\d+)\s*秒/, /每\s*(\d+)\s*秒/],
              5,
            ),
            hint: /中文(?:释义|意思)|显示中文|朗读中文/.test(text)
              ? 'meaning' as const
              : 'phonetic' as const,
            repeatCount: extractNumber(text, [/朗读\s*(\d+)\s*次/, /重复\s*(\d+)\s*次/], 2),
          },
        }
      : {}),
  }
}

const sampleVocabulary = (name: string): VocabularyDraft => ({
  subject: 'english',
  name,
  description: '由 Agent 根据当前学习需求整理的词库，可继续在词库详情中编辑。',
  category: '日常表达',
  tags: ['Agent 创建'],
  entries: [
    {
      id: id('word'),
      word: 'notice',
      phonetic: '/ˈnəʊtɪs/',
      partOfSpeech: 'v.',
      meanings: ['注意到', '留意'],
      example: 'Did you notice the change?',
      exampleTranslation: '你注意到这个变化了吗？',
    },
    {
      id: id('word'),
      word: 'routine',
      phonetic: '/ruːˈtiːn/',
      partOfSpeech: 'n.',
      meanings: ['日常惯例', '固定流程'],
      example: 'A short routine helps children settle down.',
      exampleTranslation: '简短的固定流程能帮助孩子安静下来。',
    },
    {
      id: id('word'),
      word: 'patient',
      phonetic: '/ˈpeɪʃnt/',
      partOfSpeech: 'adj.',
      meanings: ['有耐心的'],
      example: 'Be patient with new learners.',
      exampleTranslation: '对初学者要有耐心。',
    },
    {
      id: id('word'),
      word: 'progress',
      phonetic: '/ˈprəʊɡres/',
      partOfSpeech: 'n.',
      meanings: ['进步', '进展'],
      example: 'Small steps still count as progress.',
      exampleTranslation: '小的进步同样算数。',
    },
  ],
})

const importedVocabulary = (fileName: string): VocabularyDraft => ({
  subject: 'english',
  name: fileName.replace(/\.(xlsx?|csv)$/i, '') || '导入词库',
  description: `从 ${fileName} 导入的家庭学习词汇，已按示例数据模拟解析。`,
  category: '导入词库',
  tags: ['Excel 导入'],
  entries: [
    {
      id: id('word'),
      word: 'schedule',
      phonetic: '/ˈʃedjuːl/',
      partOfSpeech: 'n.',
      meanings: ['日程', '计划表'],
      example: 'We made a weekly study schedule.',
      exampleTranslation: '我们制定了每周学习计划。',
    },
    {
      id: id('word'),
      word: 'encourage',
      phonetic: '/ɪnˈkʌrɪdʒ/',
      partOfSpeech: 'v.',
      meanings: ['鼓励', '支持'],
      example: 'Parents can encourage curiosity.',
      exampleTranslation: '父母可以鼓励孩子保持好奇心。',
    },
    {
      id: id('word'),
      word: 'independent',
      phonetic: '/ˌɪndɪˈpendənt/',
      partOfSpeech: 'adj.',
      meanings: ['独立的'],
      example: 'She is learning to work independently.',
      exampleTranslation: '她正在学习独立完成任务。',
    },
    {
      id: id('word'),
      word: 'explain',
      phonetic: '/ɪkˈspleɪn/',
      partOfSpeech: 'v.',
      meanings: ['解释', '说明'],
      example: 'Can you explain the word in your own way?',
      exampleTranslation: '你能用自己的话解释这个词吗？',
    },
    {
      id: id('word'),
      word: 'memory',
      phonetic: '/ˈmeməri/',
      partOfSpeech: 'n.',
      meanings: ['记忆', '记忆力'],
      example: 'Examples make new words easier to remember.',
      exampleTranslation: '例句能让新单词更容易记住。',
    },
  ],
})

const createTaskAction = (draft: TaskDraft, libraryName: string): PendingAction => ({
  id: id('action'),
  operation: 'create_task',
  title: '创建学习任务',
  description: '请检查任务配置。确认前不会写入任何任务数据。',
  target: draft.name,
  fields: [
    { label: '学习类型', value: draft.type === 'vocabulary' ? '词汇练习' : '听写练习' },
    { label: '任务模式', value: draft.mode === 'fixed' ? '固定任务' : '长期任务' },
    { label: '内容来源', value: libraryName },
    { label: '已选词条', value: `${draft.selectedEntryIds.length} 项` },
    ...(draft.mode === 'long_term'
      ? [{ label: '分组规则', value: `每组 ${draft.wordsPerGroup} 项` }]
      : []),
    ...(draft.type === 'dictation' && draft.dictation
      ? [
          { label: '听写方式', value: draft.dictation.mode === 'online' ? '线上听写' : '线下听写' },
          { label: '播放方式', value: draft.dictation.playbackMode === 'auto' ? '自动播放' : '手动播放' },
          { label: '朗读次数', value: `${draft.dictation.repeatCount} 次` },
          { label: '朗读时显示', value: draft.dictation.hint === 'phonetic' ? '音标/拼音' : '中文释义' },
        ]
      : []),
    { label: '强制答对', value: draft.repeatUntilCorrect ? '开启' : '关闭' },
  ],
  impact: '确认后将保存任务与当前词库内容快照。后续修改原词库不会影响此任务。',
  confirmLabel: '确认创建',
  payload: { taskDraft: draft },
})

const updateTaskAction = (
  task: LearningTask,
  changes: NonNullable<PendingAction['payload']['changes']>,
): PendingAction => {
  const nextCount = changes.targetCount ?? task.targetCount
  const nextGroup =
    changes.config?.wordsPerGroup ?? task.config.wordsPerGroup
  return {
    id: id('action'),
    operation: 'update_task',
    title: '修改学习任务',
    description: '以下为本次修改的前后差异，确认后才会更新任务。',
    target: task.name,
    fields: [],
    diff: [
      {
        label: '学习数量',
        before: `${task.targetCount} 项`,
        after: `${nextCount} 项`,
      },
      {
        label: '每组数量',
        before: `${task.config.wordsPerGroup} 项`,
        after: `${nextGroup} 项`,
      },
    ],
    impact: '任务内容快照保持不变。新的分组规则从下一组开始生效。',
    confirmLabel: '确认修改',
    payload: { taskId: task.id, changes },
  }
}

const deleteTaskAction = (task: LearningTask, stage: 1 | 2, stageOneId?: string): PendingAction => ({
  id: id('action'),
  operation: 'delete_task',
  title: stage === 1 ? '删除学习任务' : '再次确认删除',
  description:
    stage === 1
      ? '这是第一次确认。删除任务会同时移除其历史练习记录。'
      : '此操作不可撤销。请再次确认你要永久删除该任务及其练习记录。',
  target: task.name,
  fields: [
    { label: '任务状态', value: task.status === 'completed' ? '已完成' : '进行中' },
    { label: '学习进度', value: `${task.progress}%` },
    { label: '内容来源', value: task.libraryName },
  ],
  impact: '任务、练习 Attempt、答题记录和由此产生的错题记录将被一并删除。',
  confirmLabel: stage === 1 ? '继续删除' : '永久删除',
  danger: true,
  stage,
  payload: {
    taskId: task.id,
    ...(stageOneId ? { firstConfirmationId: stageOneId } : {}),
  } as PendingAction['payload'],
})

const pickTask = (text: string, userId: string, preferLongTerm = false): LearningTask => {
  const tasks = taskApi.list(userId)
  const quoted = findQuoted(text)
  return (
    tasks.find((task) => quoted && task.name.includes(quoted)) ??
    (preferLongTerm
      ? tasks.find((task) => task.mode === 'long_term' && task.status === 'in_progress')
      : undefined) ??
    tasks.find((task) => task.status === 'in_progress') ??
    tasks[0]
  )
}

export const mockAgent = {
  async run(
    input: { text: string; fileName?: string; fileSize?: number; fileType?: string },
    userId: string,
    emit: Emit,
  ): Promise<void> {
    const executionId = id('execution')
    try {
      emit({
        type: 'progress',
        data: { stage: 'thinking', message: '正在理解你的需求' },
      })
      await wait(420)

      if (input.fileName) {
        const draft = importedVocabulary(input.fileName)
        await emitTool(
          emit,
          'material.parse',
          '解析学习资料',
          { file: input.fileName, size: input.fileSize, type: input.fileType },
          () => ({
            name: draft.name,
            count: draft.entries.length,
          }),
          (result) => `识别 ${result.count} 个词条，字段映射已生成`,
        )
        emit({
          type: 'message',
          data: {
            content:
              '文件已解析为演示数据。我识别到 **词形、词义、例句** 三个核心字段，并完成了去重检查。请确认字段映射和导入结果。',
          },
        })
        emit({
          type: 'confirmation_required',
          data: {
            id: id('action'),
            operation: 'import_vocabulary',
            title: '导入词库',
            description: '解析结果尚未保存。确认后将创建个人词库。',
            target: draft.name,
            fields: [
              { label: '源文件', value: input.fileName },
              { label: '解析词条', value: `${draft.entries.length} 项` },
              { label: '字段映射', value: '单词 → word，词义 → meaning，例句 → example' },
              { label: '去重结果', value: '未发现重复词条' },
              { label: '保存位置', value: '我的词库' },
            ],
            impact: '确认后将生成一个独立个人词库；原始文件不进入正式业务数据。',
            confirmLabel: '确认导入',
            payload: { vocabularyDraft: draft, fileName: input.fileName },
          },
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      const text = input.text.trim()
      if (!text) {
        emit({
          type: 'message',
          data: { content: '可以告诉我你想创建什么学习任务吗？' },
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (
        /学习记录|正确率|错题|掌握情况|学习情况/.test(text) &&
        !/创建|新建|安排|生成|修改|删除/.test(text)
      ) {
        const stats = await emitTool(
          emit,
          'learning.summary',
          '汇总学习记录',
          { scope: 'current_user' },
          () => learningApi.getStats(userId),
          (result) => `已汇总 ${result.practiceCount} 次练习`,
        )
        emit({
          type: 'message',
          data: {
            content: `这是你当前的学习概况：\n\n| 指标 | 数据 |\n| --- | ---: |\n| 已完成练习 | ${stats.practiceCount} 次 |\n| 平均正确率 | ${stats.averageAccuracy}% |\n| 已掌握词数 | ${stats.masteredCount} 个 |\n| 待复习错题 | ${stats.reviewCount} 个 |\n\n最近一次练习是 **${stats.recentAttempts[0] ? taskApi.get(stats.recentAttempts[0].taskId, userId).name : '暂无记录'}**。你可以进入学习记录查看完整错题和最近练习。`,
            links: [{ label: '打开学习记录', to: '/learning' }],
          },
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (
        /删除|移除/.test(text) &&
        /任务/.test(text)
      ) {
        const task = pickTask(text, userId)
        if (!task) {
          emit({ type: 'error', data: { code: 'task_not_found', message: '没有找到可以删除的任务。' } })
          emit({ type: 'done', data: { executionId } })
          return
        }
        await emitTool(
          emit,
          'task.inspect_delete',
          '检查删除影响',
          { task_id: task.id },
          () => ({ task: task.name, practices: task.name }),
          (result) => `已定位任务「${result.task}」`,
        )
        emit({
          type: 'message',
          data: {
            content:
              '删除任务需要两阶段确认。下面是第一次确认，确认后我还会再次核对删除对象和影响。',
          },
        })
        emit({ type: 'confirmation_required', data: deleteTaskAction(task, 1) })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (/修改|调整|改成|改为/.test(text) && /任务/.test(text)) {
        const task = pickTask(text, userId, true)
        if (!task) {
          emit({ type: 'error', data: { code: 'task_not_found', message: '没有找到可以修改的任务。' } })
          emit({ type: 'done', data: { executionId } })
          return
        }
        if (task.mode === 'fixed') {
          emit({
            type: 'message',
            data: {
              content: `「${task.name}」是固定任务，学习内容创建后不能修改。若需要调整内容，请删除后重新创建；本次没有写入任何数据。`,
              quickReplies: ['删除这个任务', '创建一个新的词汇任务'],
            },
          })
          emit({ type: 'done', data: { executionId } })
          return
        }
        const requested = extractNumber(
          text,
          [/改成\s*(\d+)\s*个/, /调整为\s*(\d+)\s*个/, /每天\s*(\d+)\s*个/],
          Math.min(task.targetCount, 8),
        )
        const targetCount = Math.min(requested, task.snapshot.length)
        const wordsPerGroup = Math.min(task.config.wordsPerGroup, targetCount)
        await emitTool(
          emit,
          'task.preview_update',
          '生成任务修改预览',
          { task_id: task.id, target_count: targetCount },
          () => ({ targetCount }),
          (result) => `目标数量将调整为 ${result.targetCount} 项`,
        )
        emit({
          type: 'message',
          data: {
            content: `我找到了任务「${task.name}」。修改后的配置如下，请确认；当前尚未更新任何数据。`,
          },
        })
        emit({
          type: 'confirmation_required',
          data: updateTaskAction(task, {
            targetCount,
            config: {
              ...task.config,
              questionCount: targetCount,
              wordsPerGroup,
              totalGroups: Math.ceil(targetCount / wordsPerGroup),
            },
          }),
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (/创建|新建|安排|生成/.test(text) && /任务/.test(text)) {
        const taskType = taskTypeFromText(text)
        if (!taskType) {
          emit({
            type: 'message',
            data: {
              content:
                '可以。你需要创建**词汇练习**还是**听写练习**？我还会确认使用哪个词库、练习数量和任务模式。',
              quickReplies: [
                '创建一个固定的词汇任务，每天 10 个词',
                '创建一个长期的听写任务，每天 6 个词',
              ],
            },
          })
          emit({ type: 'done', data: { executionId } })
          return
        }
        const draft = await emitTool(
          emit,
          'task.prepare',
          '整理任务配置',
          { type: taskType, source: 'conversation' },
          () => taskDraftFromText(text, userId, taskType),
          (result) => `已整理 ${result.targetCount} 项学习内容`,
        )
        const library = vocabularyApi.listMine(userId).find((item) => item.id === draft.libraryId)
        emit({
          type: 'message',
          data: {
            content:
              draft.mode === 'long_term'
              ? '配置已整理。长期任务会保存创建时的词库快照，因此后续修改原词库不会影响任务内容。'
              : '配置已整理。固定任务创建后不能修改学习内容；如需调整，需要删除后重新创建。',
          },
        })
        emit({
          type: 'confirmation_required',
          data: createTaskAction(draft, library?.name ?? '未命名词库'),
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (/导入|Excel|CSV/i.test(text)) {
        emit({
          type: 'message',
          data: {
            content: '请点击输入框左侧的附件按钮上传 `.xlsx` 或 `.csv` 文件。我会先模拟解析并展示字段映射，确认后才保存词库。',
          },
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      if (/词库/.test(text) && /创建|新建|整理/.test(text)) {
        const name = findQuoted(text) ?? '家庭共学 · 新词库'
        const draft = sampleVocabulary(name)
        await emitTool(
          emit,
          'vocabulary.prepare',
          '整理词库内容',
          { name, entries: draft.entries.length },
          () => ({ count: draft.entries.length }),
          (result) => `已准备 ${result.count} 个示例词条`,
        )
        emit({
          type: 'message',
          data: {
            content:
              '我先整理了一个可直接体验的词库草稿。你也可以在确认后进入词库详情继续添加、批量编辑或删除词条。',
          },
        })
        emit({
          type: 'confirmation_required',
          data: {
            id: id('action'),
            operation: 'create_vocabulary',
            title: '创建个人词库',
            description: '请检查词库名称、分类和示例词条。确认前不会保存。',
            target: draft.name,
            fields: [
              { label: '词库名称', value: draft.name },
              { label: '分类', value: draft.category },
              { label: '词条数量', value: `${draft.entries.length} 项` },
              { label: '来源', value: 'Agent 整理' },
            ],
            impact: '确认后该词库将出现在“我的词库”中，并且只属于当前用户。',
            confirmLabel: '确认创建词库',
            payload: { vocabularyDraft: draft },
          },
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      emit({
        type: 'message',
        data: {
          content: `我可以帮你把学习需求整理成可执行的业务操作。当前可以处理：\n\n- 创建、修改或删除学习任务\n- 导入 Excel / CSV 词库\n- 创建个人词库\n- 查询学习记录和错题概况\n\n你可以直接描述目标，例如“创建一个词汇任务，每天 8 个词”。`,
          quickReplies: [
            '创建一个固定的词汇任务，每天 8 个词',
            '查看我的学习记录',
            '创建一个家庭共学词库',
          ],
        },
      })
      emit({ type: 'done', data: { executionId } })
    } catch (error) {
      emit({
        type: 'error',
        data: {
          code: 'agent_error',
          message: error instanceof Error ? error.message : 'Agent 执行失败',
        },
      })
      emit({ type: 'done', data: { executionId } })
    }
  },

  async confirm(action: PendingAction, userId: string, emit: Emit): Promise<void> {
    const executionId = id('execution')
    try {
      if (action.operation === 'delete_task' && action.stage === 1) {
        emit({
          type: 'progress',
          data: { stage: 'validating_delete', message: '正在进行删除前校验' },
        })
        await wait(420)
        const task = await emitTool(
          emit,
          'task.validate_delete',
          '校验删除条件',
          { task_id: action.payload.taskId },
          () => {
            if (!action.payload.taskId) throw new Error('缺少任务 ID')
            return taskApi.get(action.payload.taskId, userId)
          },
          (result) => `已确认任务「${result.name}」及关联记录`,
        )
        emit({
          type: 'message',
          data: {
            content: `第一次确认已记录。请最后核对：任务「${task.name}」及其全部练习记录将被永久删除，此操作不可撤销。`,
          },
        })
        emit({
          type: 'confirmation_required',
          data: deleteTaskAction(task, 2, action.id),
        })
        emit({ type: 'done', data: { executionId } })
        return
      }

      emit({
        type: 'progress',
        data: { stage: 'executing_action', message: '正在执行已确认的操作' },
      })
      const result = await emitTool(
        emit,
        `action.${action.operation}`,
        action.title,
        { action_id: action.id, target: action.target },
        () => actionApi.execute(action, userId),
        (output) => output.message,
      )
      emit({
        type: 'message',
        data: {
          content: result.message,
          links: result.link ? [result.link] : undefined,
        },
      })
      emit({ type: 'done', data: { executionId } })
    } catch (error) {
      emit({
        type: 'error',
        data: {
          code: 'action_failed',
          message: error instanceof Error ? error.message : '操作执行失败',
        },
      })
      emit({ type: 'done', data: { executionId } })
    }
  },
}
