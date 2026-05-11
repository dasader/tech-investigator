import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export const createTechInput = (data: {
  category: string;
  description: string;
  user_email?: string;
  search_source?: string;
}) => api.post("/tech-input", data).then(r => r.data);

export const generateIndicators = (queryId: number) =>
  api.post(`/queries/${queryId}/indicators/generate`).then(r => r.data);

export const updateIndicator = (id: number, data: Partial<{ name: string; unit: string; confirmed_by_user: boolean }>) =>
  api.put(`/indicators/${id}`, data).then(r => r.data);

export const deleteIndicator = (id: number) =>
  api.delete(`/indicators/${id}`);

export const startJob = (queryId: number) =>
  api.post(`/queries/${queryId}/jobs`).then(r => r.data);

export const getJob = (jobId: number) =>
  api.get(`/jobs/${jobId}`).then(r => r.data);

export const getResults = (jobId: number) =>
  api.get(`/jobs/${jobId}/results`).then(r => r.data);
