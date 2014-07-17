#include <poll.h>
#include <stdio.h>
#include <signal.h>
#include <stdint.h>
#include <unistd.h>
#include <strings.h>
#include <inttypes.h>
#include <sys/time.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <sys/socket.h>

#include "proc_report.h"

// #define DEBUG

#if defined(DEBUG)
#define TRACE0(fmt, ...) printf("[%s:%d] " fmt "\n", __FILE__, __LINE__, ##__VA_ARGS__)
#define TRACE(...)       TRACE0(__VA_ARGS__)
#else
#define TRACE(...)
#endif

int
proc_get_server_socket(int port)
{
  struct sockaddr_in server;
  int s;

  s = socket(AF_INET, SOCK_STREAM, 0);
  if (s == -1) {
    perror("socket()");
    return -1;
  }

  int reuse = 1;
  if (setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) == -1) {
    perror("setsockopt()");
    close(s);
    return -1;
  }

  bzero((char*)&server, sizeof(server));
  server.sin_family = AF_INET;
  server.sin_addr.s_addr = INADDR_ANY;
  server.sin_port = ntohs(port);
  if (bind(s, (struct sockaddr*)&server, sizeof(server)) == -1) {
    perror("bind()");
    close(s);
    return -1;
  }

  if (listen(s, 8) == -1) {
    perror("listen()");
    close(s);
    return -1;
  }

  return s;
}

static void
sig_alrm_handler(int signum)
{
  // do nothing
}

int
main(void)
{
  struct itimerval new_value;

  bzero(&new_value, sizeof(new_value));
  new_value.it_interval.tv_sec = 1;
  new_value.it_value.tv_sec = 1;

  int server = proc_get_server_socket(26600);
  if (server < 0) {
    return __LINE__;
  }

  struct pollfd pfds[2];
  pfds[0].fd = server;
  pfds[0].events = POLLIN;
  pfds[1].events = POLLHUP | POLLPRI | POLLERR | POLLNVAL | POLLMSG | POLLREMOVE | POLLRDHUP | POLLRDBAND| POLLWRBAND;

  if (signal(SIGALRM, sig_alrm_handler) == SIG_ERR) {
    perror("signal()");
    return __LINE__;
  }

  int client = -1;
  int nfds = 1;
  while (1) {
    TRACE("----------\n");
    pfds[0].revents = 0;
    if (client != -1) {
      TRACE();
      nfds = 2;
      pfds[1].fd = client;
      pfds[1].revents = 0;
    } else {
      TRACE();
      nfds = 1;
    }

    TRACE();
    int rv = poll(pfds, nfds, -1 /* INFTIM */);
    if (rv < 0) {
      TRACE();
      if (client == -1 || errno != EINTR) {
        perror("poll()");
        return __LINE__;
      }
    }

    int new_client = -1;
    TRACE();
    if ((pfds[0].revents & POLLIN) == POLLIN) {
      int fd = accept(server, NULL, 0);
      TRACE();
      if (client != -1) {
        TRACE();
        close(fd);
      } else {
        TRACE();
        new_client = fd;
        bzero(&new_value, sizeof(new_value));
        new_value.it_interval.tv_sec = 1;
        new_value.it_value.tv_sec = 1;
        if (setitimer(ITIMER_REAL, &new_value, NULL) == -1) {
          perror("setitimer()");
          return __LINE__;
        }
      }
    }
    if (client != -1) {
      TRACE("pfds[1].revents = 0x%x", pfds[1].revents);
      if (pfds[1].revents & (POLLHUP | POLLRDHUP)) {
        TRACE();
        bzero(&new_value, sizeof(new_value));
        if (setitimer(ITIMER_REAL, &new_value, NULL) == -1) {
          perror("setitimer()");
          return __LINE__;
        }
        close(client);
        client = -1;
      }
    }
        
    if (client != -1) {
      TRACE();
      write(client, ">>>\n", 4);

      struct timespec start;
      struct timespec end;

      clock_gettime(CLOCK_MONOTONIC, &start);
      proc_write_report(client);
      clock_gettime(CLOCK_MONOTONIC, &end);

      if (end.tv_nsec < start.tv_nsec) {
        end.tv_nsec += 1000000000L;
        end.tv_sec -= 1;
      }
      unsigned long delta = end.tv_sec - start.tv_sec;
      delta *= 1000000UL;
      delta += (end.tv_nsec - start.tv_nsec) / 1000;
      printf("---> proc_write_report() took %lu us\n", delta);

      write(client, "<<<\n", 4);
    }
    if (new_client != -1) {
      client = new_client;
    }
  }

  return 0;
}
