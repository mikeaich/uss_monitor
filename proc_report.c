#include "proc_report.h"

#include <dirent.h>
#include <stdint.h>
#include <unistd.h>
#include <inttypes.h>

#include "red_black_tree.h"

// #define DEBUG

#if defined(DEBUG)
#define TRACE0(fmt, ...) printf("[%s:%d] " fmt "\n", __FILE__, __LINE__, ##__VA_ARGS__)
#define TRACE(...)       TRACE0(__VA_ARGS__)
#else
#define TRACE(...)
#endif

typedef unsigned int bool;
static const bool true = 1;
static const bool false = 0;

typedef struct {
  pid_t       pid;
  pid_t       ppid;
  const char* name;
  size_t      uss;
  size_t      new_uss;
  uint64_t    updated;
  bool        is_new;
} process_info;

int
tree_key_compare(const void* a, const void* b)
{
  const pid_t aa = (pid_t)a;
  const pid_t bb = (pid_t)b;

  if (aa > bb) return 1;
  if (aa < bb) return -1;
  return 0;
}

void
tree_key_destroy(void* key)
{
  pid_t pid = (pid_t)key;
  TRACE("destroy key, pid=%u\n", pid);
}

void
tree_node_destroy(void* node)
{
  process_info* n = (process_info*)node;
  TRACE("destroy node, pid=%u\n", n->pid);
  free(n);
}

void
tree_key_dump(const void* key)
{
  pid_t pid = (pid_t)key;
  TRACE("dump key, pid=%u\n", pid);
}

void
tree_node_dump(void* node)
{
  process_info* info = (process_info*)node;
  TRACE("dump node, pid=%u\n", info->pid);
}

static rb_red_blk_tree* processes = NULL;

int
proc_write_report(int fd)
{
  static uint64_t iteration = 0;
  static pid_t max_pid = 0;

  if (!processes) {
    processes = RBTreeCreate(tree_key_compare,
                             tree_key_destroy,
                             tree_node_destroy,
                             tree_key_dump,
                             tree_node_dump);
    if (!processes) {
      return 0;
    }
  }

  DIR* dp;
  struct dirent* ep;     
  dp = opendir("/proc/");
  pid_t b2g_pid = 0;
  char buf[1024];
  int len;

  ++iteration;

  if (dp != NULL) {
    while ((ep = readdir(dp))) {
      pid_t pid;

      if (sscanf(ep->d_name, "%u", &pid) == 1) {
        TRACE("pid = %u\n", pid);
        if (pid > max_pid) {
          max_pid = pid;
        }
        snprintf(buf, sizeof(buf), "/proc/%u/smaps", pid);
        FILE* f = fopen(buf, "r");
        if (f) {
          uint64_t uss = 0;
          while (fgets(buf, sizeof(buf), f)) {
            uint64_t val;
            if (sscanf(buf, "Private_Dirty: %" PRIu64 " kB", &val) == 1 ||
                sscanf(buf, "Private_Clean: %" PRIu64 " kB", &val) == 1) {
              uss += val * 1024UL;
            }
          }
          fclose(f);
          TRACE("uss = %" PRIu64 "\n", uss);

          rb_red_blk_node* process;
          process_info* info;
          if ((process = RBExactQuery(processes, (void*)pid)) == NULL) {
            TRACE();
            // this process is new, add it to the tree
            info = malloc(sizeof(process_info));

            // get the process name, if it exists
            snprintf(buf, sizeof(buf), "/proc/%u/comm", pid);
            f = fopen(buf, "r");
            *buf = '\0';
            if (f) {
              fgets(buf, sizeof(buf), f);
              len = strlen(buf);
              if (buf[len - 1] == '\n') {
                // get rid of the newline
                buf[len - 1] = '\0';
              }
              info->name = strdup(buf);
              fclose(f);
            } else {
              info->name = NULL;
            }

            // try to get the new process' parent process ID
            info->ppid = 0;
            snprintf(buf, sizeof(buf), "/proc/%u/status", pid);
            f = fopen(buf, "r");
            if (f) {
              while (fgets(buf, sizeof(buf), f)) {
                if (sscanf(buf, "PPid: %u", &info->ppid) == 1) {
                  break;
                }
              }
              fclose(f);
            }
            TRACE("ppid = %u\n", info->ppid);

            info->is_new = true;
            info->pid = pid;
            RBTreeInsert(processes, (void*)pid, info);
          } else {
            info = (process_info*)process->info;
          }

          info->new_uss = uss;
          info->updated = iteration;
        }
      }
    }

    closedir(dp);

    stk_stack* stack = RBEnumerate(processes, (void*)1, (void*)max_pid);
    rb_red_blk_node* process;
    while ((process = StackPop(stack))) {
      process_info* info = (process_info*)process->info;
      len = 0;
      if (info->updated != iteration) {
        TRACE();
        // this record wasn't updated, so this process no longer exists
        len = snprintf(buf, sizeof(buf), "old/ pid %u\n", info->pid);
        RBDelete(processes, process);
      } else if (info->is_new) {
        TRACE();
        info->is_new = false;
        if (info->name) {
          len = snprintf(buf, sizeof(buf), "new/ pid %u, ppid %u, name %s\n", info->pid, info->ppid, info->name);
        } else {
          len = snprintf(buf, sizeof(buf), "new/ pid %u, ppid %u\n", info->pid, info->ppid);
        }
      } else if (info->uss != info->new_uss) {
        TRACE();
        len = snprintf(buf, sizeof(buf), "update/ pid %u uss %u\n", info->pid, info->new_uss);
        info->uss = info->new_uss;
      } else {
        TRACE();
      }
      if (len) {
        write(fd, buf, len);
      }
    }
  } else {
    perror("opendir()");
  }

  return 0;
}
