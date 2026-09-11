import { AfterViewInit, Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

type MenuItem = { label: string; route: string };

@Component({ selector:'app-header', standalone:true, templateUrl:'./header.component.html', styleUrl:'./header.component.css' })
export class HeaderComponent implements AfterViewInit {
  private readonly router = inject(Router);
  @ViewChild('logoCanvas') private readonly logoCanvas?: ElementRef<HTMLCanvasElement>;
  readonly menuItems: MenuItem[] = [
    { label:'Task thread', route:'/task-thread' }, { label:'Monorepo agents', route:'/agents' },
    { label:'Workflows', route:'/workflows' }, { label:'Memory system', route:'/memory' }, { label:'Work logs', route:'/work-logs' },
    { label:'Agent messaging portal', route:'/messaging' }
  ];
  readonly currentUrl = signal(this.router.url);

  constructor() { this.router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd)).subscribe((event) => this.currentUrl.set(event.urlAfterRedirects)); }
  ngAfterViewInit(): void {
    const canvas = this.logoCanvas?.nativeElement; if (!canvas) return;
    const context = canvas.getContext('2d'); if (!context) return;
    context.clearRect(0, 0, 32, 32); context.lineWidth = 1.5; context.lineJoin = 'round';
    context.fillStyle = '#dce6e1'; context.beginPath(); context.moveTo(16,3); context.lineTo(28,9); context.lineTo(16,15); context.lineTo(4,9); context.closePath(); context.fill();
    context.fillStyle = '#78988d'; context.beginPath(); context.moveTo(4,9); context.lineTo(16,15); context.lineTo(16,29); context.lineTo(4,23); context.closePath(); context.fill();
    context.fillStyle = '#48675e'; context.beginPath(); context.moveTo(28,9); context.lineTo(16,15); context.lineTo(16,29); context.lineTo(28,23); context.closePath(); context.fill();
    context.strokeStyle = '#242521'; context.stroke();
  }
  navigate(route: string): void { this.router.navigateByUrl(route); }
  selected(route: string): boolean { return this.currentUrl().startsWith(route); }
}
