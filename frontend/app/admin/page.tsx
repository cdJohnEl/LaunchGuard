"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Shield,
  Search,
  Plus,
  Trash2,
  Edit3,
  RefreshCw,
  Lock,
  Unlock,
  Check,
  Copy,
  ExternalLink,
  AlertTriangle,
  MessageSquare,
  Users,
  Radio,
  Sliders,
  X,
  ArrowUpDown,
  Server,
} from "lucide-react";
import {
  GroupDoc,
  AdminStats,
  fetchAdminStats,
  fetchAdminGroups,
  createAdminGroup,
  updateAdminGroup,
  deleteAdminGroup,
  getAdminBackendUrl,
} from "@/lib/adminApi";

const STORAGE_KEY = "launchguard:admin_key";
const BACKEND_URL_KEY = "launchguard:admin_backend_url";
const DEFAULT_ADMIN_KEY = "launchguard_admin_2026";

export default function AdminDashboardPage() {
  const [adminKey, setAdminKey] = useState<string>("");
  const [inputKey, setInputKey] = useState<string>("");
  const [backendUrl, setBackendUrl] = useState<string>("");
  const [inputBackendUrl, setInputBackendUrl] = useState<string>("");
  const [isAuthorized, setIsAuthorized] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Data states
  const [loading, setLoading] = useState<boolean>(false);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [groups, setGroups] = useState<GroupDoc[]>([]);
  const [search, setSearch] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "inactive" | "claimed" | "unclaimed">("all");
  const [sortBy, setSortBy] = useState<"recent" | "blocked" | "name">("recent");
  const [notification, setNotification] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Modals state
  const [editGroup, setEditGroup] = useState<GroupDoc | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [groupToDelete, setGroupToDelete] = useState<GroupDoc | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Add form fields
  const [newChatId, setNewChatId] = useState<string>("");
  const [newGroupName, setNewGroupName] = useState<string>("");
  const [newActive, setNewActive] = useState<boolean>(true);
  const [newOwnerUid, setNewOwnerUid] = useState<string>("");

  // Edit form state
  const [editName, setEditName] = useState<string>("");
  const [editActive, setEditActive] = useState<boolean>(true);
  const [editOwnerUid, setEditOwnerUid] = useState<string>("");
  const [editStatus, setEditStatus] = useState<string>("trial");
  const [editBlocked, setEditBlocked] = useState<number>(0);
  const [editKeywords, setEditKeywords] = useState<string[]>([]);
  const [newKeywordInput, setNewKeywordInput] = useState<string>("");
  const [editFaqPairs, setEditFaqPairs] = useState<Record<string, string>>({});
  const [newFaqKey, setNewFaqKey] = useState<string>("");
  const [newFaqVal, setNewFaqVal] = useState<string>("");
  const [isSavingEdit, setIsSavingEdit] = useState<boolean>(false);

  // On mount: check stored key
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) || DEFAULT_ADMIN_KEY;
    const storedUrl = window.localStorage.getItem(BACKEND_URL_KEY) || getAdminBackendUrl();
    setBackendUrl(storedUrl);
    setInputBackendUrl(storedUrl);
    setInputKey(stored);
    if (stored) {
      verifyAndLoad(stored);
    }
  }, []);

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const verifyAndLoad = async (key: string) => {
    setLoading(true);
    setAuthError(null);
    try {
      const [statsData, groupsData] = await Promise.all([
        fetchAdminStats(key),
        fetchAdminGroups(key),
      ]);
      setStats(statsData);
      setGroups(groupsData);
      setAdminKey(key);
      setIsAuthorized(true);
      window.localStorage.setItem(STORAGE_KEY, key);
    } catch (err: any) {
      setIsAuthorized(false);
      setAuthError(err.message || "Failed to authenticate with backend.");
    } finally {
      setLoading(false);
    }
  };

  const refreshData = async () => {
    if (!adminKey) return;
    setLoading(true);
    try {
      const [statsData, groupsData] = await Promise.all([
        fetchAdminStats(adminKey),
        fetchAdminGroups(adminKey),
      ]);
      setStats(statsData);
      setGroups(groupsData);
      showToast("Data refreshed from Firestore.");
    } catch (err: any) {
      showToast(err.message || "Refresh failed", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleUnlock = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputBackendUrl) {
      window.localStorage.setItem(BACKEND_URL_KEY, inputBackendUrl.trim());
      setBackendUrl(inputBackendUrl.trim());
    }
    verifyAndLoad(inputKey.trim());
  };

  const handleSignOut = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setAdminKey("");
    setIsAuthorized(false);
    setGroups([]);
    setStats(null);
  };

  // Quick toggle group active status
  const toggleGroupActive = async (group: GroupDoc) => {
    try {
      const updated = await updateAdminGroup(adminKey, group.chat_id, {
        active: !group.active,
      });
      setGroups((prev) =>
        prev.map((g) => (g.chat_id === group.chat_id ? { ...g, active: updated.active } : g))
      );
      showToast(`Chat ${group.chat_id} is now ${updated.active ? "Active" : "Inactive"}`);
    } catch (err: any) {
      showToast(err.message || "Toggle failed", "error");
    }
  };

  // Open Edit Drawer
  const openEditModal = (group: GroupDoc) => {
    setEditGroup(group);
    setEditName(group.group_name || "");
    setEditActive(group.active);
    setEditOwnerUid(group.owner_uid || "");
    setEditStatus(group.subscription_status || "trial");
    setEditBlocked(group.scams_blocked || 0);
    setEditKeywords(group.scam_keywords || []);
    setEditFaqPairs(group.faq_pairs || {});
    setNewKeywordInput("");
    setNewFaqKey("");
    setNewFaqVal("");
  };

  // Save Edit Changes
  const handleSaveEdit = async () => {
    if (!editGroup) return;
    setIsSavingEdit(true);
    try {
      const updates = {
        group_name: editName.trim() || editGroup.group_name,
        active: editActive,
        owner_uid: editOwnerUid.trim() ? editOwnerUid.trim() : null,
        subscription_status: editStatus,
        scams_blocked: Number(editBlocked),
        scam_keywords: editKeywords,
        faq_pairs: editFaqPairs,
      };

      const updated = await updateAdminGroup(adminKey, editGroup.chat_id, updates);
      setGroups((prev) =>
        prev.map((g) => (g.chat_id === editGroup.chat_id ? { ...g, ...updated } : g))
      );
      setEditGroup(null);
      showToast(`Group "${updated.group_name}" updated successfully!`);
    } catch (err: any) {
      showToast(err.message || "Failed to update group", "error");
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Delete Group
  const handleConfirmDelete = async () => {
    if (!groupToDelete) return;
    try {
      await deleteAdminGroup(adminKey, groupToDelete.chat_id);
      setGroups((prev) => prev.filter((g) => g.chat_id !== groupToDelete.chat_id));
      showToast(`Group ${groupToDelete.chat_id} deleted permanently.`);
      setGroupToDelete(null);
      if (stats) {
        setStats({
          ...stats,
          total_groups: Math.max(0, stats.total_groups - 1),
          active_groups: groupToDelete.active ? Math.max(0, stats.active_groups - 1) : stats.active_groups,
        });
      }
    } catch (err: any) {
      showToast(err.message || "Delete failed", "error");
    }
  };

  // Create New Group
  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsedChatId = parseInt(newChatId.trim(), 10);
    if (isNaN(parsedChatId)) {
      showToast("Chat ID must be a valid integer number (e.g. -1004490491313)", "error");
      return;
    }
    if (!newGroupName.trim()) {
      showToast("Group title is required", "error");
      return;
    }

    try {
      const created = await createAdminGroup(adminKey, {
        chat_id: parsedChatId,
        group_name: newGroupName.trim(),
        active: newActive,
        owner_uid: newOwnerUid.trim() ? newOwnerUid.trim() : null,
        subscription_status: "trial",
      });
      setGroups((prev) => [created, ...prev]);
      setIsAddModalOpen(false);
      setNewChatId("");
      setNewGroupName("");
      setNewOwnerUid("");
      showToast(`Group "${created.group_name}" created successfully!`);
    } catch (err: any) {
      showToast(err.message || "Failed to create group", "error");
    }
  };

  // Filtered & Sorted Groups
  const filteredGroups = useMemo(() => {
    let result = groups.filter((g) => {
      const q = search.toLowerCase();
      const matchSearch =
        (g.group_name || "").toLowerCase().includes(q) ||
        String(g.chat_id).includes(q) ||
        (g.owner_uid || "").toLowerCase().includes(q);

      if (!matchSearch) return false;

      if (filterStatus === "active") return g.active;
      if (filterStatus === "inactive") return !g.active;
      if (filterStatus === "claimed") return Boolean(g.owner_uid);
      if (filterStatus === "unclaimed") return !g.owner_uid;
      return true;
    });

    if (sortBy === "blocked") {
      result.sort((a, b) => (b.scams_blocked || 0) - (a.scams_blocked || 0));
    } else if (sortBy === "name") {
      result.sort((a, b) => (a.group_name || "").localeCompare(b.group_name || ""));
    } else {
      result.sort(
        (a, b) =>
          new Date(b.updated_at || b.created_at || 0).getTime() -
          new Date(a.updated_at || a.created_at || 0).getTime()
      );
    }

    return result;
  }, [groups, search, filterStatus, sortBy]);

  // Auth lock screen
  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center p-4 font-sans text-ink">
        <div className="max-w-md w-full bg-white border border-rule rounded-xl p-8 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-ink text-paper flex items-center justify-center">
              <Shield className="w-5 h-5 text-signal" />
            </div>
            <div>
              <h1 className="text-xl font-bold font-display">LaunchGuard Admin</h1>
              <p className="text-xs text-ink-soft">Master Management & Onboarding Console</p>
            </div>
          </div>

          {authError && (
            <div className="mb-4 p-3 bg-signal-tint border border-signal/20 rounded-lg text-sm text-signal flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleUnlock} className="space-y-4">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                Admin Secret Key
              </label>
              <input
                type="password"
                value={inputKey}
                onChange={(e) => setInputKey(e.target.value)}
                placeholder="Enter LaunchGuard Admin Key"
                className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono"
                required
              />
              <p className="text-[11px] text-ink-faint mt-1">
                Default key is configured in backend environment (<code className="bg-gray-100 px-1 rounded">launchguard_admin_2026</code>).
              </p>
            </div>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                Backend Server URL
              </label>
              <input
                type="text"
                value={inputBackendUrl}
                onChange={(e) => setInputBackendUrl(e.target.value)}
                placeholder="https://launchguard-qo47.onrender.com"
                className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-ink text-paper font-medium rounded-lg text-sm hover:bg-ink-hover transition flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" /> Verifying...
                </>
              ) : (
                <>
                  <Unlock className="w-4 h-4" /> Unlock Admin Console
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-rule text-center">
            <Link href="/dashboard" className="text-xs text-ink-soft hover:text-ink underline">
              ← Return to Founder Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper font-sans text-ink">
      {/* Toast Notification */}
      {notification && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm flex items-center gap-2 border ${
            notification.type === "success"
              ? "bg-white text-ink border-emerald-500 shadow-emerald-500/10"
              : "bg-signal-tint text-signal border-signal/30"
          }`}
        >
          {notification.type === "success" ? (
            <Check className="w-4 h-4 text-emerald-600" />
          ) : (
            <AlertTriangle className="w-4 h-4" />
          )}
          <span>{notification.text}</span>
        </div>
      )}

      {/* Top Navigation */}
      <header className="border-b border-rule bg-white sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-ink text-paper flex items-center justify-center">
              <Shield className="w-4 h-4 text-signal" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base font-display">LaunchGuard</span>
                <span className="px-2 py-0.5 text-[10px] font-mono uppercase bg-rule rounded-full font-medium">
                  Admin Console
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Server className="w-3 h-3 text-emerald-600" />
                <span className="font-mono text-[11px] truncate max-w-[200px] sm:max-w-xs">{backendUrl}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={refreshData}
              disabled={loading}
              title="Refresh Firestore data"
              className="p-2 border border-rule hover:border-ink rounded-lg text-ink-soft hover:text-ink transition flex items-center gap-1 text-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Refresh</span>
            </button>

            <Link
              href="/dashboard"
              className="px-3 py-1.5 border border-rule hover:border-ink rounded-lg text-xs font-medium text-ink-soft hover:text-ink transition"
            >
              Founder View
            </Link>

            <Link
              href="/"
              target="_blank"
              className="px-3 py-1.5 border border-rule hover:border-ink rounded-lg text-xs font-medium text-ink-soft hover:text-ink transition flex items-center gap-1"
            >
              <span>Landing</span>
              <ExternalLink className="w-3 h-3" />
            </Link>

            <button
              onClick={handleSignOut}
              className="px-3 py-1.5 bg-rule hover:bg-rule-strong rounded-lg text-xs font-medium text-ink transition flex items-center gap-1"
            >
              <Lock className="w-3 h-3" />
              <span>Lock</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
        {/* KPI Summary Cards */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white border border-rule rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-ink-soft mb-2">
              <span className="text-xs font-mono uppercase tracking-wider">Total Groups</span>
              <Users className="w-4 h-4" />
            </div>
            <div className="text-3xl font-display font-bold text-ink">
              {stats?.total_groups ?? groups.length}
            </div>
            <p className="text-xs text-ink-soft mt-1">Onboarded across Telegram</p>
          </div>

          <div className="bg-white border border-rule rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-ink-soft mb-2">
              <span className="text-xs font-mono uppercase tracking-wider">Active Guarding</span>
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            </div>
            <div className="text-3xl font-display font-bold text-emerald-600">
              {stats?.active_groups ?? groups.filter((g) => g.active).length}
            </div>
            <p className="text-xs text-ink-soft mt-1">Actively deleting scams</p>
          </div>

          <div className="bg-white border border-rule rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-ink-soft mb-2">
              <span className="text-xs font-mono uppercase tracking-wider">Scams Blocked</span>
              <Shield className="w-4 h-4 text-signal" />
            </div>
            <div className="text-3xl font-display font-bold text-signal">
              {stats?.total_blocked ?? groups.reduce((acc, g) => acc + (g.scams_blocked || 0), 0)}
            </div>
            <p className="text-xs text-ink-soft mt-1">Cumulative scam deletions</p>
          </div>

          <div className="bg-white border border-rule rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between text-ink-soft mb-2">
              <span className="text-xs font-mono uppercase tracking-wider">Claimed by Founders</span>
              <Radio className="w-4 h-4 text-ink-soft" />
            </div>
            <div className="text-3xl font-display font-bold text-ink">
              {stats?.claimed_groups ?? groups.filter((g) => g.owner_uid).length}
              <span className="text-base text-ink-faint font-normal"> / {groups.length}</span>
            </div>
            <p className="text-xs text-ink-soft mt-1">Bound to founder dashboard</p>
          </div>
        </section>

        {/* Action Controls & Filtering Bar */}
        <section className="bg-white border border-rule rounded-xl p-4 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                type="text"
                placeholder="Search by Group Name, Chat ID (-100...), or Founder UID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-sans"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink text-xs"
                >
                  Clear
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center border border-rule rounded-lg p-1 bg-paper text-xs">
                {(["all", "active", "inactive", "claimed", "unclaimed"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setFilterStatus(tab)}
                    className={`px-2.5 py-1 rounded capitalize font-medium transition ${
                      filterStatus === tab
                        ? "bg-white text-ink shadow-xs"
                        : "text-ink-soft hover:text-ink"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              <button
                onClick={() => setIsAddModalOpen(true)}
                className="px-3.5 py-2 bg-ink text-paper rounded-lg text-xs font-medium hover:bg-ink-hover transition flex items-center gap-1.5 shrink-0"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Onboard Group</span>
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-ink-soft pt-2 border-t border-rule/60">
            <div>
              Showing <span className="font-semibold text-ink">{filteredGroups.length}</span> of{" "}
              {groups.length} groups
            </div>
            <div className="flex items-center gap-2">
              <span className="text-ink-faint">Sort by:</span>
              <select
                value={sortBy}
                onChange={(e: any) => setSortBy(e.target.value)}
                className="bg-transparent border border-rule rounded px-2 py-0.5 text-xs text-ink focus:outline-none"
              >
                <option value="recent">Recently Updated</option>
                <option value="blocked">Most Scams Blocked</option>
                <option value="name">Group Name (A-Z)</option>
              </select>
            </div>
          </div>
        </section>

        {/* Groups Data Table */}
        <section className="bg-white border border-rule rounded-xl shadow-xs overflow-hidden">
          {filteredGroups.length === 0 ? (
            <div className="py-16 text-center text-ink-soft">
              <Users className="w-10 h-10 mx-auto text-ink-faint mb-3 stroke-[1.5]" />
              <h3 className="font-display font-medium text-lg text-ink">No groups found</h3>
              <p className="text-xs text-ink-soft max-w-sm mx-auto mt-1">
                {search
                  ? "No communities match your search filters."
                  : "No groups have been onboarded yet. Add your bot to a Telegram group or click 'Onboard Group' above."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-paper border-b border-rule text-[11px] font-mono uppercase tracking-wider text-ink-soft">
                  <tr>
                    <th className="py-3 px-4">Group / Community</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Founder Claim</th>
                    <th className="py-3 px-4 text-center">Scams Blocked</th>
                    <th className="py-3 px-4 text-center">FAQ Pairs</th>
                    <th className="py-3 px-4">Last Sync</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {filteredGroups.map((group) => {
                    const hasOwner = Boolean(group.owner_uid);
                    const faqCount = Object.keys(group.faq_pairs || {}).length;
                    return (
                      <tr key={group.chat_id} className="hover:bg-paper/50 transition">
                        {/* Group Name & ID */}
                        <td className="py-3.5 px-4">
                          <div className="font-medium text-ink flex items-center gap-1.5">
                            <span>{group.group_name || "Unnamed Group"}</span>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rule/70 uppercase">
                              {group.subscription_status || "trial"}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 text-xs text-ink-soft font-mono mt-0.5">
                            <span>{group.chat_id}</span>
                            <button
                              onClick={() => copyToClipboard(String(group.chat_id), `chat-${group.chat_id}`)}
                              className="text-ink-faint hover:text-ink"
                              title="Copy Chat ID"
                            >
                              {copiedId === `chat-${group.chat_id}` ? (
                                <Check className="w-3 h-3 text-emerald-600" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                        </td>

                        {/* Status (Toggle switch) */}
                        <td className="py-3.5 px-4">
                          <button
                            onClick={() => toggleGroupActive(group)}
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition ${
                              group.active
                                ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                                : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                            }`}
                            title="Click to toggle active status"
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                group.active ? "bg-emerald-500" : "bg-gray-400"
                              }`}
                            />
                            <span>{group.active ? "Active" : "Inactive"}</span>
                          </button>
                        </td>

                        {/* Owner / Claimed */}
                        <td className="py-3.5 px-4">
                          {hasOwner ? (
                            <div className="flex items-center gap-1.5 font-mono text-xs text-ink">
                              <span className="px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded">
                                …{group.owner_uid?.slice(-6)}
                              </span>
                              <button
                                onClick={() => copyToClipboard(group.owner_uid || "", `owner-${group.chat_id}`)}
                                className="text-ink-faint hover:text-ink"
                                title="Copy full UID"
                              >
                                {copiedId === `owner-${group.chat_id}` ? (
                                  <Check className="w-3 h-3 text-emerald-600" />
                                ) : (
                                  <Copy className="w-3 h-3" />
                                )}
                              </button>
                            </div>
                          ) : (
                            <span className="inline-block px-2 py-0.5 text-xs font-mono rounded bg-amber-50 text-amber-700 border border-amber-200">
                              Unclaimed
                            </span>
                          )}
                        </td>

                        {/* Scams Blocked */}
                        <td className="py-3.5 px-4 text-center">
                          <span className="inline-flex items-center gap-1 font-mono font-bold text-signal bg-signal-tint/60 px-2.5 py-0.5 rounded-full text-xs">
                            <Shield className="w-3 h-3" />
                            {group.scams_blocked || 0}
                          </span>
                        </td>

                        {/* FAQ Pairs */}
                        <td className="py-3.5 px-4 text-center">
                          <span className="inline-flex items-center gap-1 font-mono text-xs px-2 py-0.5 rounded bg-rule/50 text-ink">
                            <MessageSquare className="w-3 h-3 text-ink-faint" />
                            {faqCount}
                          </span>
                        </td>

                        {/* Last Sync */}
                        <td className="py-3.5 px-4 text-xs text-ink-soft">
                          {group.updated_at
                            ? new Date(group.updated_at).toLocaleDateString()
                            : group.created_at
                            ? new Date(group.created_at).toLocaleDateString()
                            : "—"}
                        </td>

                        {/* Actions */}
                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => openEditModal(group)}
                              className="p-1.5 text-ink-soft hover:text-ink hover:bg-rule/40 rounded transition"
                              title="Edit group configuration"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setGroupToDelete(group)}
                              className="p-1.5 text-ink-faint hover:text-signal hover:bg-signal-tint rounded transition"
                              title="Delete group permanently"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {/* ================= MODAL: EDIT GROUP (FULL CRUD) ================= */}
      {editGroup && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white border border-rule rounded-xl max-w-2xl w-full p-6 shadow-xl my-8 space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-rule">
              <div>
                <h3 className="font-display font-bold text-lg text-ink">Manage Community</h3>
                <p className="text-xs text-ink-soft font-mono">Chat ID: {editGroup.chat_id}</p>
              </div>
              <button
                onClick={() => setEditGroup(null)}
                className="text-ink-faint hover:text-ink p-1 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-5 max-h-[65vh] overflow-y-auto pr-1">
              {/* Basic Details */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                    Group Title
                  </label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-sans"
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                    Subscription Tier
                  </label>
                  <select
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                    className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink bg-white"
                  >
                    <option value="trial">Trial</option>
                    <option value="active">Active (Paid)</option>
                    <option value="vip">VIP / Partner</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                    Scams Blocked Counter
                  </label>
                  <input
                    type="number"
                    value={editBlocked}
                    onChange={(e) => setEditBlocked(parseInt(e.target.value, 10) || 0)}
                    className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                    Guarding Status
                  </label>
                  <div className="flex items-center gap-3 pt-2">
                    <label className="flex items-center gap-2 cursor-pointer text-sm">
                      <input
                        type="checkbox"
                        checked={editActive}
                        onChange={(e) => setEditActive(e.target.checked)}
                        className="w-4 h-4 rounded border-rule text-ink focus:ring-ink"
                      />
                      <span className="font-medium">{editActive ? "Active" : "Disabled"}</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Ownership */}
              <div className="pt-4 border-t border-rule">
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft">
                    Founder UID (Owner)
                  </label>
                  {editOwnerUid && (
                    <button
                      type="button"
                      onClick={() => setEditOwnerUid("")}
                      className="text-xs text-signal hover:underline"
                    >
                      Unclaim Group (Release)
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  value={editOwnerUid}
                  onChange={(e) => setEditOwnerUid(e.target.value)}
                  placeholder="Firebase Auth UID of group owner (or empty for unclaimed)"
                  className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono text-xs"
                />
                <p className="text-[11px] text-ink-faint mt-1">
                  Unclaiming releases this group so a founder can claim it via <code className="bg-gray-100 px-1 rounded">/claim &lt;code&gt;</code> in Telegram.
                </p>
              </div>

              {/* Custom Scam Blacklist Keywords */}
              <div className="pt-4 border-t border-rule space-y-3">
                <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft">
                  Custom Scam Keywords ({editKeywords.length})
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newKeywordInput}
                    onChange={(e) => setNewKeywordInput(e.target.value)}
                    placeholder="Add custom scam keyword (e.g. presale-live)..."
                    className="flex-1 px-3 py-1.5 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (newKeywordInput.trim()) {
                          setEditKeywords([...editKeywords, newKeywordInput.trim()]);
                          setNewKeywordInput("");
                        }
                      }
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (newKeywordInput.trim()) {
                        setEditKeywords([...editKeywords, newKeywordInput.trim()]);
                        setNewKeywordInput("");
                      }
                    }}
                    className="px-3 py-1.5 bg-ink text-paper text-xs rounded-lg font-medium"
                  >
                    Add
                  </button>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {editKeywords.map((kw, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-signal-tint text-signal text-xs font-mono"
                    >
                      <span>{kw}</span>
                      <button
                        type="button"
                        onClick={() => setEditKeywords(editKeywords.filter((_, i) => i !== idx))}
                        className="hover:text-ink"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                  {editKeywords.length === 0 && (
                    <span className="text-xs text-ink-faint italic">No custom scam keywords configured yet.</span>
                  )}
                </div>
              </div>

              {/* FAQ Pairs Management */}
              <div className="pt-4 border-t border-rule space-y-3">
                <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft">
                  FAQ Pairs ({Object.keys(editFaqPairs).length})
                </label>

                {/* Add new pair */}
                <div className="p-3 bg-paper border border-rule rounded-lg space-y-2">
                  <span className="text-xs font-medium text-ink block">Add New FAQ Auto-Responder:</span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input
                      type="text"
                      placeholder="Trigger keyword (e.g. contract address)"
                      value={newFaqKey}
                      onChange={(e) => setNewFaqKey(e.target.value)}
                      className="px-3 py-1.5 border border-rule rounded text-xs bg-white focus:outline-none"
                    />
                    <input
                      type="text"
                      placeholder="Bot reply text..."
                      value={newFaqVal}
                      onChange={(e) => setNewFaqVal(e.target.value)}
                      className="px-3 py-1.5 border border-rule rounded text-xs bg-white focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (newFaqKey.trim() && newFaqVal.trim()) {
                        setEditFaqPairs({ ...editFaqPairs, [newFaqKey.trim()]: newFaqVal.trim() });
                        setNewFaqKey("");
                        setNewFaqVal("");
                      }
                    }}
                    className="px-3 py-1 bg-ink text-paper text-xs rounded font-medium"
                  >
                    Add FAQ Rule
                  </button>
                </div>

                {/* List pairs */}
                <div className="space-y-2">
                  {Object.entries(editFaqPairs).map(([keyword, reply]) => (
                    <div
                      key={keyword}
                      className="p-2.5 border border-rule rounded-lg flex items-start justify-between gap-3 text-xs"
                    >
                      <div className="space-y-0.5 flex-1">
                        <div className="font-mono font-semibold text-ink">Keyword: &quot;{keyword}&quot;</div>
                        <div className="text-ink-soft font-display italic">&quot;{reply}&quot;</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          const copy = { ...editFaqPairs };
                          delete copy[keyword];
                          setEditFaqPairs(copy);
                        }}
                        className="text-ink-faint hover:text-signal p-1 rounded"
                        title="Delete FAQ pair"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-rule">
              <button
                type="button"
                onClick={() => setEditGroup(null)}
                className="px-4 py-2 border border-rule rounded-lg text-sm text-ink-soft hover:text-ink font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={isSavingEdit}
                className="px-5 py-2 bg-ink text-paper rounded-lg text-sm font-medium hover:bg-ink-hover transition flex items-center gap-2"
              >
                {isSavingEdit ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Saving...
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4" /> Save Changes
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ================= MODAL: ONBOARD / CREATE GROUP ================= */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-rule rounded-xl max-w-md w-full p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-rule">
              <h3 className="font-display font-bold text-lg text-ink">Onboard New Community</h3>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="text-ink-faint hover:text-ink"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateGroup} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                  Telegram Chat ID *
                </label>
                <input
                  type="text"
                  value={newChatId}
                  onChange={(e) => setNewChatId(e.target.value)}
                  placeholder="e.g. -1004490491313"
                  className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono"
                  required
                />
                <p className="text-[11px] text-ink-faint mt-1">
                  Telegram supergroup IDs always start with <code className="bg-gray-100 px-1 rounded">-100</code>.
                </p>
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                  Community Name *
                </label>
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="e.g. Monad Alpha Chat"
                  className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-ink-soft mb-1">
                  Founder UID (Optional)
                </label>
                <input
                  type="text"
                  value={newOwnerUid}
                  onChange={(e) => setNewOwnerUid(e.target.value)}
                  placeholder="Leave blank for unassigned"
                  className="w-full px-3 py-2 border border-rule rounded-lg text-sm focus:outline-none focus:border-ink font-mono text-xs"
                />
              </div>

              <div className="pt-2">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={newActive}
                    onChange={(e) => setNewActive(e.target.checked)}
                    className="w-4 h-4 rounded border-rule text-ink"
                  />
                  <span>Guarding Active immediately</span>
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-rule">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 border border-rule rounded-lg text-sm text-ink-soft hover:text-ink font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-ink text-paper rounded-lg text-sm font-medium hover:bg-ink-hover transition"
                >
                  Create Group
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ================= MODAL: DELETE CONFIRMATION ================= */}
      {groupToDelete && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-rule rounded-xl max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="w-10 h-10 rounded-full bg-signal-tint text-signal flex items-center justify-center mb-1">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-display font-bold text-lg text-ink">Delete Group Permanently?</h3>
              <p className="text-xs text-ink-soft mt-1 leading-relaxed">
                Are you sure you want to remove <span className="font-semibold text-ink">&quot;{groupToDelete.group_name}&quot;</span> (Chat ID: {groupToDelete.chat_id})? This will delete all its FAQ pairs and settings from Firestore.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-rule">
              <button
                type="button"
                onClick={() => setGroupToDelete(null)}
                className="px-4 py-2 border border-rule rounded-lg text-sm text-ink-soft hover:text-ink font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="px-4 py-2 bg-signal text-white rounded-lg text-sm font-medium hover:bg-red-700 transition"
              >
                Delete Group
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

