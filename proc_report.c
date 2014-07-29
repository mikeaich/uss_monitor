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

typedef enum {
  PS_UNKNOWN,     // process status is unknown
  PS_NEW,         // process was created just before this iteration
  PS_IDLE,        // process has not changed vitals since last iteration
  PS_UPDATED,     // process has changed vitals since last iteration
  PS_RENAMED      // process has changed names
} PROCESS_STATUS;

typedef struct {
  pid_t           pid;
  pid_t           ppid;
  const char*     name;
  const char*     new_name;
  size_t          uss;
  size_t          new_uss;
  PROCESS_STATUS  status;
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
proc_write_report(int fd, int sync)
{
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

  struct dirent*  ep;     
  pid_t           b2g_pid = 0;
  char            buf[1024];
  DIR*            dp;
  int             len;

  dp = opendir("/proc/");

  if (dp) {
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
          // calculate USS: the total size of all of the private data held
          // by this process.
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

          // get the internal name of the process, if it exists
          const char* name = NULL;
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
            name = strdup(buf);
            fclose(f);
          }
          
          rb_red_blk_node* process = RBExactQuery(processes, (void*)pid);
          process_info* info;
          if (!process) {
            TRACE();
            // this process is new, add it to the tree
            info = malloc(sizeof(process_info));
            info->status = PS_NEW;

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

            info->pid = pid;
            info->uss = uss;
            info->name = name;

            RBTreeInsert(processes, (void*)pid, info);
          } else {
            TRACE();
            // this process already exists, update its record
            info = (process_info*)process->info;
            info->status = PS_IDLE;

            if (uss != info->uss) {
              info->status = PS_UPDATED;
              info->uss = uss;
            }

            // this case must appear last
            if (!info->name || !name || strcmp(info->name, name) != 0) {
              info->status = PS_RENAMED;
              free((void*)info->name);
              info->name = name;
            } else {
              free(name);
            }
          }
        }
      }
    }

    closedir(dp);

    stk_stack* stack = RBEnumerate(processes, (void*)1, (void*)max_pid);
    rb_red_blk_node* process;
    while ((process = StackPop(stack))) {
      process_info* info = (process_info*)process->info;
      PROCESS_STATUS status = info->status;

      if (sync) {
        status = PS_NEW;
      }
      len = 0;
      switch (status) {
        case PS_UNKNOWN:
          TRACE();
          // this record wasn't updated, so this process no longer exists
          len = snprintf(buf, sizeof(buf), "old|pid=%u\n", info->pid);
          RBDelete(processes, process);
          break;

        case PS_NEW:
          TRACE();
          if (info->name) {
            len = snprintf(buf, sizeof(buf), "new|pid=%u|ppid=%u|uss=%u|name=%s\n",
                           info->pid, info->ppid, info->uss, info->name);
          } else {
            len = snprintf(buf, sizeof(buf), "new|pid=%u|ppid=%u|uss=%u\n",
                           info->pid, info->ppid, info->uss);
          }
          break;

        case PS_UPDATED:
          TRACE();
          len = snprintf(buf, sizeof(buf), "update|pid=%u|uss=%u\n",
                         info->pid, info->uss);
          break;

        case PS_RENAMED:
          TRACE();
          len = snprintf(buf, sizeof(buf), "update|pid=%u|uss=%u|name=%s\n",
                         info->pid, info->uss, info->name);
          break;

        case PS_IDLE:
        default:
          // nothing to do
          break;
      }
      if (len) {
        if (write(fd, buf, len) < 0) {
          perror("write()");
          return -1;
        }
      }
      info->status = PS_UNKNOWN; // reset state to unknown
    }
    free(stack);
  } else {
    perror("opendir()");
  }

  return 0;
}
