/**
 * api.js — every call the pages make to the backend goes through here.
 *
 * Each function lists the FastAPI route it maps to. While CONFIG.USE_MOCK is
 * true the same functions are answered by services/mock/mockApi.js instead,
 * so the pages never need to change when you switch to the real server.
 *
 * Field names are snake_case to match the Python/PostgreSQL side.
 */
import { CONFIG } from '../config.js';
import { request } from './http.js';

const real = {
  /* ---------- auth & account ---------- */
  login: body => request('/auth/login', { method: 'POST', body }),               // {email,password} → {token,user}
  signup: body => request('/auth/signup', { method: 'POST', body }),             // {name,email,password} → {token,user}
  logout: () => request('/auth/logout', { method: 'POST' }),
  getMe: () => request('/users/me'),                                              // → {id,name,email,photo_url}
  updateMe: body => request('/users/me', { method: 'PATCH', body }),             // {name?,email?,photo_url?}
  changePassword: body => request('/users/me/password', { method: 'POST', body }),// {current_password,new_password}
  getEstimates: () => request('/users/me/estimates'),                             // → {finished_tasks,threshold,model_ready,model_synthetic}

  /* ---------- goals ---------- */
  getActiveGoals: () => request('/goals?status=active'),                         // → [goal, …] (a user can have several)
  createGoal: body => request('/goals', { method: 'POST', body }),               // {title,deadline,daily_available_hours,available_days}
  decomposeGoal: id => request(`/goals/${id}/decompose`, { method: 'POST' }),     // → {milestones,tasks,checks,used_fallback}
  createSchedule: (id, body) => request(`/goals/${id}/schedule`, { method: 'POST', body }), // {excluded_task_ids}
  updatePreferences: (id, body) => request(`/goals/${id}`, { method: 'PATCH', body }),

  /* ---------- plan ---------- */
  getTasks: id => request(`/goals/${id}/tasks`),
  getSchedule: id => request(`/goals/${id}/schedule`),                            // → {version,today,assignments:[{date,task_id,planned_hours}]}
  getStatus: id => request(`/goals/${id}/status`),                                // feasibility numbers
  getFixOptions: id => request(`/goals/${id}/fix-options`),
  applyFix: (id, body) => request(`/goals/${id}/adjust`, { method: 'POST', body }), // {kind,value,consent}
  getUpdates: id => request(`/goals/${id}/updates`),

  /* ---------- tasks & reviews ---------- */
  updateTask: (taskId, body) => request(`/tasks/${taskId}`, { method: 'PATCH', body }),                 // e.g. {subtasks}
  recordProgress: (taskId, body) => request(`/tasks/${taskId}/progress`, { method: 'POST', body }),     // {actual_hours_spent,remaining_hours}
  submitDailyReview: (id, body) => request(`/goals/${id}/daily-review`, { method: 'POST', body }),     // {date,items:[{task_id,status,actual_hours_spent,remaining_hours}]}
  getReviews: id => request(`/goals/${id}/daily-reviews`),
  getPendingReviews: id => request(`/goals/${id}/pending-reviews`),                                   // → {dates:[...]} oldest first

  /* ---------- notifications (bell in the sidebar) ---------- */
  getNotifications: () => request('/notifications'),                                                  // → {unread, items:[{id,kind,title,body,link,created_at,read}]}
  markNotificationRead: id => request(`/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () => request('/notifications/read-all', { method: 'POST' }),
};

// The mock backend is only downloaded when it's used.
export const api = CONFIG.USE_MOCK ? await import('./mock/mockApi.js') : real;
