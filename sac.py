"""SAC: 1 Q, krytyk z privileged state, bufor sukcesów."""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal


LOG_STD_MIN = -5.0
LOG_STD_MAX = 2.0


def _mlp(in_dim, hidden, out_dim):
    return nn.Sequential(
        nn.Linear(in_dim, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, out_dim),
    )


class Actor(nn.Module):
    def __init__(self, obs_dim, act_dim, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.mean = nn.Linear(hidden, act_dim)
        self.log_std = nn.Linear(hidden, act_dim)

    def forward(self, obs):
        h = self.net(obs)
        mean = self.mean(h)
        log_std = self.log_std(h)
        log_std = torch.tanh(log_std)
        log_std = LOG_STD_MIN + 0.5 * (LOG_STD_MAX - LOG_STD_MIN) * (log_std + 1.0)
        return mean, log_std

    def sample(self, obs):
        mean, log_std = self.forward(obs)
        std = log_std.exp()
        dist = Normal(mean, std)
        x = dist.rsample()
        action = torch.tanh(x)
        log_prob = dist.log_prob(x) - torch.log(1.0 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        return action, log_prob

    def act(self, obs, deterministic=False):
        mean, log_std = self.forward(obs)
        if deterministic:
            return torch.tanh(mean)
        std = log_std.exp()
        return torch.tanh(Normal(mean, std).sample())


class Critic(nn.Module):
    """Q(s_priv, a) — s_priv może być bogatsze niż obserwacja aktora."""

    def __init__(self, state_dim, act_dim, hidden=256):
        super().__init__()
        # sklejony wektor stanu (s_priv + 2 (v, kąt))
        self.q = _mlp(state_dim + act_dim, hidden, 1)

    def forward(self, state, action):
        #sklejenie
        x = torch.cat([state, action], dim=-1)
        return self.q(x)


class ReplayBuffer:
    def __init__(self, capacity, obs_dim, priv_dim, act_dim):
        self.capacity = int(capacity)
        self.obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.next_obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.priv = np.zeros((self.capacity, priv_dim), dtype=np.float32)
        self.next_priv = np.zeros((self.capacity, priv_dim), dtype=np.float32)
        self.actions = np.zeros((self.capacity, act_dim), dtype=np.float32)
        self.rewards = np.zeros((self.capacity, 1), dtype=np.float32)
        self.dones = np.zeros((self.capacity, 1), dtype=np.float32)
        # indeks gdzie moge wpisac kolejny wpis
        self.idx = 0
        self.size = 0

    def add(self, obs, priv, action, reward, next_obs, next_priv, done):
        self.obs[self.idx] = obs
        self.priv[self.idx] = priv
        self.actions[self.idx] = action
        self.rewards[self.idx] = reward
        self.next_obs[self.idx] = next_obs
        self.next_priv[self.idx] = next_priv
        self.dones[self.idx] = done
        self.idx = (self.idx + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size, device):
        idxs = np.random.randint(0, self.size, size=batch_size)
        return (
            torch.as_tensor(self.obs[idxs], device=device),
            torch.as_tensor(self.priv[idxs], device=device),
            torch.as_tensor(self.actions[idxs], device=device),
            torch.as_tensor(self.rewards[idxs], device=device),
            torch.as_tensor(self.next_obs[idxs], device=device),
            torch.as_tensor(self.next_priv[idxs], device=device),
            torch.as_tensor(self.dones[idxs], device=device),
        )


class SACAgent:
    def __init__(
        self,
        obs_dim,
        act_dim,
        device,
        priv_dim=None,
        hidden=256,
        lr=3e-4,
        gamma=0.99,
        tau=0.005,
        batch_size=256,
        buffer_size=200_000,
        success_buffer_size=50_000,
        autotune_alpha=True,
        init_alpha=0.2,
        success_frac=0.25,
    ):
        self.obs_dim = obs_dim
        self.priv_dim = int(priv_dim if priv_dim is not None else obs_dim)
        self.act_dim = act_dim
        self.device = device
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.success_frac = success_frac

        self.actor = Actor(obs_dim, act_dim, hidden).to(device)
        self.critic = Critic(self.priv_dim, act_dim, hidden).to(device)
        self.critic_target = Critic(self.priv_dim, act_dim, hidden).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())

        self.actor_opt = torch.optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(), lr=lr)

        self.autotune_alpha = autotune_alpha
        self.target_entropy = -float(act_dim)
        if autotune_alpha:
            self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
            self.alpha_opt = torch.optim.Adam([self.log_alpha], lr=lr)
            self.alpha = self.log_alpha.exp().item()
        else:
            self.log_alpha = None
            self.alpha = init_alpha

        self.buffer = ReplayBuffer(buffer_size, obs_dim, self.priv_dim, act_dim)
        self.success_buffer = ReplayBuffer(
            success_buffer_size, obs_dim, self.priv_dim, act_dim
        )

    def act(self, obs, deterministic=False):
        with torch.no_grad():
            x = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
            action = self.actor.act(x, deterministic=deterministic)
        return action.squeeze(0).cpu().numpy()

    def remember(self, obs, priv, action, reward, next_obs, next_priv, terminated):
        self.buffer.add(
            obs, priv, action, reward, next_obs, next_priv, float(terminated)
        )

    def remember_success(self, obs, priv, action, reward, next_obs, next_priv, terminated):
        self.success_buffer.add(
            obs, priv, action, reward, next_obs, next_priv, float(terminated)
        )

    def _sample_batch(self):
        n_succ = 0
        if self.success_buffer.size >= 32:
            n_succ = int(self.batch_size * self.success_frac)
            n_succ = min(n_succ, self.success_buffer.size)
        n_main = self.batch_size - n_succ
        if n_main > self.buffer.size:
            return None
        batch = self.buffer.sample(n_main, self.device)
        if n_succ > 0:
            extra = self.success_buffer.sample(n_succ, self.device)
            batch = tuple(torch.cat([a, b], dim=0) for a, b in zip(batch, extra))
        return batch

    def update(self):
        if self.buffer.size < self.batch_size:
            return None
        batch = self._sample_batch()
        if batch is None:
            return None
        obs, priv, actions, rewards, next_obs, next_priv, dones = batch

        with torch.no_grad():
            next_actions, next_log_prob = self.actor.sample(next_obs)
            q_t = self.critic_target(next_priv, next_actions) - self.alpha * next_log_prob
            target = rewards + (1.0 - dones) * self.gamma * q_t

        q = self.critic(priv, actions)
        critic_loss = F.mse_loss(q, target)
        self.critic_opt.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic.parameters(), 1.0)
        self.critic_opt.step()

        pi, log_prob = self.actor.sample(obs)
        q_pi = self.critic(priv, pi)
        actor_loss = (self.alpha * log_prob - q_pi).mean()

        self.actor_opt.zero_grad()
        actor_loss.backward()
        nn.utils.clip_grad_norm_(self.actor.parameters(), 1.0)
        self.actor_opt.step()

        if self.autotune_alpha:
            alpha_loss = -(self.log_alpha * (log_prob + self.target_entropy).detach()).mean()
            self.alpha_opt.zero_grad()
            alpha_loss.backward()
            self.alpha_opt.step()
            self.alpha = self.log_alpha.exp().item()

        self._soft_update()
        return {
            "critic": float(critic_loss.item()),
            "actor": float(actor_loss.item()),
            "alpha": float(self.alpha),
        }

    def _soft_update(self):
        with torch.no_grad():
            for param, target in zip(
                self.critic.parameters(), self.critic_target.parameters()
            ):
                target.data.mul_(1.0 - self.tau)
                target.data.add_(self.tau * param.data)

    def save(self, path, extra=None):
        payload = {
            "algo": "sac",
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "obs_dim": self.obs_dim,
            "priv_dim": self.priv_dim,
            "act_dim": self.act_dim,
        }
        if extra:
            payload.update(extra)
        torch.save(payload, path)

    @classmethod
    def load(cls, path, device):
        try:
            ckpt = torch.load(path, map_location=device, weights_only=False)
        except TypeError:
            ckpt = torch.load(path, map_location=device)
        obs_dim = int(ckpt["obs_dim"])
        act_dim = int(ckpt["act_dim"])
        priv_dim = int(ckpt.get("priv_dim", obs_dim))
        agent = cls(obs_dim, act_dim, device, priv_dim=priv_dim)
        agent.actor.load_state_dict(ckpt["actor"])
        if "critic" in ckpt:
            try:
                agent.critic.load_state_dict(ckpt["critic"])
                agent.critic_target.load_state_dict(ckpt["critic"])
            except RuntimeError:
                pass
        agent.actor.eval()
        return agent, ckpt
